# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations/{org_id}/webhooks endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.common import PaginatedResponse
from auth.api.schemas.api.organisations import (
    CreateWebhookRequest,
    UpdateWebhookRequest,
    WebhookCreateResponse,
    WebhookDeliveryEnqueuedResponse,
    WebhookDeliveryResponse,
    WebhookEventsCatalogResponse,
    WebhookResponse,
    WebhookSecretResponse,
)
from auth.db.models.tenant import (
    TenantWebhook,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEvent,
)
from auth.db.models.user import User
from auth.services.webhook import (
    WebhookURLError,
    generate_secret,
    validate_target_url,
    webhook_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["organisation-webhooks"])

_VALID_EVENT_VALUES: set[str] = {e.value for e in WebhookEvent}
_EVENT_GROUPS: set[str] = {e.value.split(".", 1)[0] for e in WebhookEvent}


def _sanitize_events(selected: list[str]) -> list[str]:
    """Keep exact event values, recognised group wildcards, and the global ``*``."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in selected:
        value = raw.strip()
        if not value or value in seen:
            continue
        if value == "*" or value in _VALID_EVENT_VALUES:
            out.append(value)
            seen.add(value)
            continue
        if value.endswith(".*"):
            prefix = value[:-2]
            if prefix in _EVENT_GROUPS or any(
                e.value.startswith(prefix + ".") for e in WebhookEvent
            ):
                out.append(value)
                seen.add(value)
    return out


def _webhook_to_response(webhook: TenantWebhook) -> WebhookResponse:
    return WebhookResponse(
        id=webhook.id,
        tenant_id=webhook.tenant_id,
        name=webhook.name,
        url=webhook.url,
        events=list(webhook.events or []),
        headers=dict(webhook.headers or {}),
        is_active=webhook.is_active,
        last_triggered_at=webhook.last_triggered_at,
        last_status_code=webhook.last_status_code,
        last_error=webhook.last_error,
        failure_count=webhook.failure_count,
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
    )


def _delivery_to_response(delivery: WebhookDelivery) -> WebhookDeliveryResponse:
    status_value = (
        delivery.status.value
        if isinstance(delivery.status, WebhookDeliveryStatus)
        else delivery.status
    )
    return WebhookDeliveryResponse(
        id=delivery.id,
        webhook_id=delivery.webhook_id,
        event=delivery.event,
        status=status_value,
        attempt=delivery.attempt,
        max_attempts=delivery.max_attempts,
        request_url=delivery.request_url,
        request_headers=dict(delivery.request_headers or {}),
        response_status=delivery.response_status,
        response_headers=dict(delivery.response_headers) if delivery.response_headers else None,
        response_body=delivery.response_body,
        error=delivery.error,
        duration_ms=delivery.duration_ms,
        delivered_at=delivery.delivered_at,
        next_retry_at=delivery.next_retry_at,
        created_at=delivery.created_at,
    )


async def _get_org_webhook(
    db: AsyncSession, org_id: uuid.UUID, webhook_id: uuid.UUID
) -> TenantWebhook:
    """Load a webhook or 404; also enforces tenant isolation."""
    webhook = await webhook_service.get_for_tenant(db, tenant_id=org_id, webhook_id=webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return webhook


@router.get("/events", response_model=WebhookEventsCatalogResponse)
async def list_org_webhook_events(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> WebhookEventsCatalogResponse:
    """List all subscribable webhook event types for an organisation.

    Returns every recognised event key grouped by its dot-notation prefix (e.g.
    `user`, `member`, `oauth2`). Use these values in the `events` array when
    creating or updating a webhook. The wildcard `*` and group wildcards like
    `user.*` are also accepted.

    **Required scope:** org membership + `webhooks:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/events
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:read")

    groups: dict[str, list[str]] = {}
    for event in WebhookEvent:
        prefix = event.value.split(".", 1)[0]
        groups.setdefault(prefix, []).append(event.value)
    for key in groups:
        groups[key].sort()

    return WebhookEventsCatalogResponse(groups=dict(sorted(groups.items())))


@router.get("/", response_model=PaginatedResponse[WebhookResponse])
async def list_org_webhooks(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[WebhookResponse]:
    """List all webhooks registered for an organisation.

    Returns a paginated list of webhooks ordered by creation date descending.
    The signing secret is never included in list responses; use the
    `rotate-secret` endpoint to obtain a new secret.

    **Required scope:** org membership + `webhooks:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/?page=1&page_size=20"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:read")

    webhooks, total = await webhook_service.list_for_tenant(
        db, tenant_id=org_id, page=page, page_size=page_size
    )

    items = [_webhook_to_response(w) for w in webhooks]
    return PaginatedResponse[WebhookResponse](
        items=items, total=total, page=page, page_size=page_size
    )


@router.post(
    "/",
    response_model=WebhookCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_webhook(
    org_id: uuid.UUID,
    body: CreateWebhookRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> WebhookCreateResponse:
    """Create a new webhook endpoint for an organisation.

    Generates an HMAC-SHA256 signing secret and returns it in the `secret`
    field of the response — this is the only time the plaintext secret is
    exposed. Store it securely; use `rotate-secret` if it is ever lost or
    compromised. The `events` array must contain at least one recognised event
    key, group wildcard (e.g. `user.*`), or the global wildcard `*`.

    **Required scope:** org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "CI notifications", "url": "https://hooks.example.com/auth", "events": ["user.*"]}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/
    ```

    **Responses:**
    - `201` — webhook created; `secret` present in body
    - `400` — invalid URL or unrecognised event keys
    - `403` — missing required scope
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:write")

    events = _sanitize_events(body.events)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="events must contain at least one recognised event or wildcard",
        )

    try:
        validate_target_url(body.url)
    except WebhookURLError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    secret = generate_secret()
    webhook = await webhook_service.create_for_tenant(
        db,
        tenant_id=org_id,
        name=body.name,
        url=body.url,
        events=events,
        secret=secret,
        headers=body.headers,
        is_active=body.is_active,
    )

    logger.info(
        "ACTION: org_webhook_create, user_id=%s, org_id=%s, webhook_id=%s",
        user.id,
        org_id,
        webhook.id,
    )

    return WebhookCreateResponse(
        webhook=_webhook_to_response(webhook),
        secret=secret,
    )


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_org_webhook(
    org_id: uuid.UUID,
    webhook_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> WebhookResponse:
    """Retrieve a single webhook by ID.

    Returns the full webhook record including delivery statistics (`failure_count`,
    `last_status_code`, `last_error`) but never the signing secret. Only webhooks
    belonging to the specified organisation are accessible.

    **Required scope:** org membership + `webhooks:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```

    **Responses:**
    - `200` — webhook found
    - `403` — missing required scope
    - `404` — webhook not found or does not belong to this organisation
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:read")

    webhook = await _get_org_webhook(db, org_id, webhook_id)
    return _webhook_to_response(webhook)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_org_webhook(
    org_id: uuid.UUID,
    webhook_id: uuid.UUID,
    body: UpdateWebhookRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> WebhookResponse:
    """Partially update a webhook's configuration.

    All fields are optional; only supplied fields are modified (PATCH semantics).
    If `events` is provided it must contain at least one valid event key or
    wildcard, otherwise the request is rejected. Updating `url` re-validates the
    target address. The signing secret is not affected; use `rotate-secret` for
    that.

    **Required scope:** org membership + `webhooks:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"is_active": false, "events": ["user.*", "member.*"]}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```

    **Responses:**
    - `200` — webhook updated
    - `400` — invalid URL or unrecognised event keys
    - `403` — missing required scope
    - `404` — webhook not found
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:write")
    webhook = await _get_org_webhook(db, org_id, webhook_id)

    update_data = body.model_dump(exclude_unset=True)

    if "events" in update_data:
        sanitized = _sanitize_events(update_data["events"] or [])
        if not sanitized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="events must contain at least one recognised event or wildcard",
            )
        webhook.events = sanitized
        update_data.pop("events")

    if "url" in update_data and update_data["url"] is not None:
        try:
            validate_target_url(update_data["url"])
        except WebhookURLError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    for field, value in update_data.items():
        if value is None and field in {"name", "url", "is_active"}:
            # PATCH semantics: only apply when an explicit non-null value is given
            continue
        setattr(webhook, field, value)

    await webhook_service.save(db, webhook)

    logger.info(
        "ACTION: org_webhook_update, user_id=%s, org_id=%s, webhook_id=%s",
        user.id,
        org_id,
        webhook.id,
    )
    return _webhook_to_response(webhook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_webhook(
    org_id: uuid.UUID,
    webhook_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> None:
    """Permanently delete a webhook and its delivery history.

    Removes the webhook record and all associated delivery attempts via cascade
    delete. This action is irreversible; any external system relying on signature
    verification with the old secret should be updated before deletion.

    **Required scope:** org membership + `webhooks:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```

    **Responses:**
    - `204` — webhook deleted
    - `403` — missing required scope
    - `404` — webhook not found
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:delete")
    webhook = await _get_org_webhook(db, org_id, webhook_id)

    await webhook_service.delete(db, webhook)

    logger.info(
        "ACTION: org_webhook_delete, user_id=%s, org_id=%s, webhook_id=%s",
        user.id,
        org_id,
        webhook_id,
    )


@router.post("/{webhook_id}/rotate-secret", response_model=WebhookSecretResponse)
async def rotate_org_webhook_secret(
    org_id: uuid.UUID,
    webhook_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> WebhookSecretResponse:
    """Rotate the HMAC-SHA256 signing secret for a webhook.

    Generates a new cryptographically random secret, replaces the stored value,
    and returns the plaintext secret once. Update your receiver's verification
    logic before rotating to avoid a gap in signature validation; deliveries
    in-flight at the time of rotation will be signed with the old secret.

    **Required scope:** org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/6ba7b810-9dad-11d1-80b4-00c04fd430c8/rotate-secret
    ```

    **Responses:**
    - `200` — new secret returned; old secret is immediately invalidated
    - `403` — missing required scope
    - `404` — webhook not found
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:write")
    webhook = await _get_org_webhook(db, org_id, webhook_id)

    new_secret = generate_secret()
    webhook.secret = new_secret
    await webhook_service.save(db, webhook)

    logger.info(
        "ACTION: org_webhook_rotate_secret, user_id=%s, org_id=%s, webhook_id=%s",
        user.id,
        org_id,
        webhook_id,
    )
    return WebhookSecretResponse(secret=new_secret)


@router.post(
    "/{webhook_id}/test",
    response_model=WebhookDeliveryEnqueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def test_org_webhook(
    org_id: uuid.UUID,
    webhook_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> WebhookDeliveryEnqueuedResponse:
    """Send a test delivery to verify a webhook endpoint is reachable.

    Creates a `webhook.test` event delivery and enqueues it immediately via
    Celery. The response contains the `delivery_id` which can be used to poll
    `/{webhook_id}/deliveries/{delivery_id}` for the outcome. The webhook must
    be active and its target URL must pass validation.

    **Required scope:** org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/6ba7b810-9dad-11d1-80b4-00c04fd430c8/test
    ```

    **Responses:**
    - `202` — delivery accepted and enqueued
    - `400` — webhook URL failed validation
    - `403` — missing required scope
    - `404` — webhook not found
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:write")
    webhook = await _get_org_webhook(db, org_id, webhook_id)

    try:
        validate_target_url(webhook.url)
    except WebhookURLError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    delivery = await webhook_service.create_test_delivery(db, webhook=webhook, triggered_by=user.id)

    logger.info(
        "ACTION: org_webhook_test, user_id=%s, org_id=%s, webhook_id=%s, delivery_id=%s",
        user.id,
        org_id,
        webhook_id,
        delivery.id,
    )
    return WebhookDeliveryEnqueuedResponse(delivery_id=delivery.id)


@router.get(
    "/{webhook_id}/deliveries",
    response_model=PaginatedResponse[WebhookDeliveryResponse],
)
async def list_org_webhook_deliveries(
    org_id: uuid.UUID,
    webhook_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[WebhookDeliveryResponse]:
    """List delivery attempts for a specific webhook.

    Returns a paginated log of all delivery attempts ordered by creation date
    descending, including HTTP response codes, duration, retry state, and any
    error messages. Useful for debugging failed deliveries before triggering a
    replay.

    **Required scope:** org membership + `webhooks:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/6ba7b810-9dad-11d1-80b4-00c04fd430c8/deliveries?page=1&page_size=20"
    ```

    **Responses:**
    - `200` — paginated delivery list
    - `403` — missing required scope
    - `404` — webhook not found
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:read")
    webhook = await _get_org_webhook(db, org_id, webhook_id)

    deliveries, total = await webhook_service.list_deliveries_for_webhook(
        db, webhook_id=webhook.id, page=page, page_size=page_size
    )

    items = [_delivery_to_response(d) for d in deliveries]
    return PaginatedResponse[WebhookDeliveryResponse](
        items=items, total=total, page=page, page_size=page_size
    )


@router.post(
    "/{webhook_id}/deliveries/{delivery_id}/replay",
    response_model=WebhookDeliveryEnqueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replay_org_webhook_delivery(
    org_id: uuid.UUID,
    webhook_id: uuid.UUID,
    delivery_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> WebhookDeliveryEnqueuedResponse:
    """Replay a past webhook delivery with a fresh envelope.

    Clones the original event payload, assigns a new delivery ID and timestamp,
    and enqueues it immediately. The replayed delivery is independent of the
    original; it starts at attempt 0 and respects the current `max_attempts`
    setting. Use this to recover from transient failures without re-triggering
    the source event.

    **Required scope:** org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/webhooks/6ba7b810-9dad-11d1-80b4-00c04fd430c8/deliveries/f47ac10b-58cc-4372-a567-0e02b2c3d479/replay
    ```

    **Responses:**
    - `202` — replay delivery accepted and enqueued
    - `403` — missing required scope
    - `404` — webhook or original delivery not found
    """
    await require_org_membership(org_id, request, db, user, required_scope="webhooks:write")
    webhook = await _get_org_webhook(db, org_id, webhook_id)

    original = await webhook_service.get_delivery_for_webhook(
        db, webhook_id=webhook.id, delivery_id=delivery_id
    )
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    replay = await webhook_service.replay_delivery(db, webhook=webhook, original=original)

    logger.info(
        "ACTION: org_webhook_replay, user_id=%s, org_id=%s, webhook_id=%s, replay_id=%s",
        user.id,
        org_id,
        webhook_id,
        replay.id,
    )
    return WebhookDeliveryEnqueuedResponse(delivery_id=replay.id)
