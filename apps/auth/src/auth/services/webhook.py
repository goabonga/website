# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Outbound tenant webhook dispatch service.

Responsibilities:
- Compute subscription match patterns for a given event (exact, nested
  group wildcards, global ``*``).
- Generate HMAC-SHA256 signatures with a timestamp prefix to prevent replay.
- Validate target URLs against an SSRF blocklist of private IP ranges.
- Persist ``WebhookDelivery`` rows and enqueue the Celery delivery task.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.tenant import (
    TenantWebhook,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEvent,
)
from auth.db.repositories.webhook import WebhookRepository

logger = logging.getLogger(__name__)

_SIGNATURE_VERSION = "v1"


class WebhookURLError(ValueError):
    """Raised when a webhook target URL is rejected (scheme, DNS, or SSRF)."""


def generate_secret() -> str:
    """Return a URL-safe random string used as an HMAC key."""
    return secrets.token_urlsafe(48)


def compute_matching_patterns(event: str) -> list[str]:
    """Return all subscription patterns that match ``event``.

    For ``mfa.challenge.failed`` the result is::

        ["mfa.challenge.failed", "*", "mfa.*", "mfa.challenge.*"]
    """
    patterns: list[str] = [event, "*"]
    parts = event.split(".")
    for i in range(1, len(parts)):
        patterns.append(".".join(parts[:i]) + ".*")
    return patterns


def sign_body(secret: str, body: bytes, timestamp: int) -> str:
    """Return the ``X-Webhook-Signature`` header value for ``body``.

    Format (Stripe-style)::

        t=<unix_ts>,v1=<hex_hmac_sha256>

    The HMAC is computed over ``f"{timestamp}.{body}"`` so replays with a
    different timestamp cannot reuse a captured signature.
    """
    payload = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},{_SIGNATURE_VERSION}={digest}"


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_target_url(url: str) -> None:
    """Raise :class:`WebhookURLError` if ``url`` is unsafe to call.

    Blocks non-http(s) schemes and, unless
    ``settings.webhook_allow_private_networks`` is set, private/loopback
    addresses (prevents SSRF into the internal network).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebhookURLError(f"Unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise WebhookURLError("URL is missing a host")

    if settings.webhook_allow_private_networks:
        return

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise WebhookURLError(f"DNS resolution failed for {parsed.hostname!r}: {e}") from e

    for info in infos:
        ip = str(info[4][0])
        if _is_private_ip(ip):
            raise WebhookURLError(f"Target {parsed.hostname!r} resolves to private address {ip}")


def build_envelope(
    *,
    event: str,
    tenant_id: uuid.UUID,
    data: dict[str, Any],
    delivery_id: uuid.UUID,
) -> dict[str, Any]:
    """Return the JSON envelope that is signed and POSTed to the target."""
    return {
        "id": str(delivery_id),
        "event": event,
        "tenant_id": str(tenant_id),
        "created_at": datetime.now(UTC).isoformat(),
        "data": data,
    }


def build_request_headers(
    *,
    webhook: TenantWebhook,
    delivery_id: uuid.UUID,
    event: str,
    attempt: int,
    body: bytes,
    timestamp: int,
) -> dict[str, str]:
    """Return the full header set sent on a delivery attempt."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "auth-webhooks/1.0",
        "X-Webhook-Id": str(webhook.id),
        "X-Webhook-Event": event,
        "X-Webhook-Delivery": str(delivery_id),
        "X-Webhook-Attempt": str(attempt),
        "X-Webhook-Signature": sign_body(webhook.secret, body, timestamp),
        "X-Webhook-Timestamp": str(timestamp),
    }
    # Custom headers take precedence except for the signature set.
    reserved = {k.lower() for k in headers}
    for key, value in (webhook.headers or {}).items():
        if key.lower() in reserved:
            continue
        headers[key] = str(value)
    return headers


class WebhookService:
    """Dispatch events to matching tenant webhooks."""

    def __init__(self, repository: WebhookRepository | None = None) -> None:
        self._repository = repository or WebhookRepository()

    async def find_matching_webhooks(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        event: str,
    ) -> list[TenantWebhook]:
        """Return active webhooks for ``tenant_id`` that subscribe to ``event``."""
        patterns = compute_matching_patterns(event)
        rows = await self._repository.list_matching_subscribed(db, tenant_id, patterns)
        return list(rows)

    # ------------------------------------------------------------------
    # CRUD helpers used by REST handlers
    # ------------------------------------------------------------------

    async def get_for_tenant(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        webhook_id: uuid.UUID,
    ) -> TenantWebhook | None:
        """Return a webhook scoped to ``tenant_id`` or ``None``."""
        return await self._repository.find_for_tenant(db, tenant_id, webhook_id)

    async def list_for_tenant(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[TenantWebhook], int]:
        """Return ``(items, total)`` for paginated webhook listing."""
        total = await self._repository.count_by_tenant(db, tenant_id)
        offset = (page - 1) * page_size
        items = await self._repository.list_by_tenant(db, tenant_id, offset=offset, limit=page_size)
        return items, total

    async def list_all_for_tenant(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
    ) -> Sequence[TenantWebhook]:
        """Return every webhook for ``tenant_id`` ordered by creation desc."""
        return await self._repository.list_all_by_tenant(db, tenant_id)

    async def list_recent_deliveries(
        self,
        db: AsyncSession,
        *,
        webhook_id: uuid.UUID,
        limit: int = 20,
    ) -> Sequence[WebhookDelivery]:
        """Return the most recent ``limit`` deliveries for ``webhook_id``."""
        return await self._repository.list_recent_deliveries(db, webhook_id, limit=limit)

    async def create_for_tenant(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        name: str,
        url: str,
        events: list[str],
        secret: str,
        headers: dict[str, Any] | None,
        is_active: bool,
    ) -> TenantWebhook:
        """Persist a new webhook and return the flushed row.

        Does not commit; caller owns the transaction boundary.
        """
        webhook = TenantWebhook(
            tenant_id=tenant_id,
            name=name,
            url=url,
            events=events,
            secret=secret,
            headers=headers or {},
            is_active=is_active,
        )
        await self._repository.add(db, webhook)
        return webhook

    async def save(self, db: AsyncSession, webhook: TenantWebhook) -> TenantWebhook:
        """Flush pending updates on ``webhook`` and return it."""
        await self._repository.flush(db)
        return webhook

    async def delete(self, db: AsyncSession, webhook: TenantWebhook) -> None:
        """Stage a webhook deletion (no commit)."""
        await self._repository.delete(db, webhook)

    # ------------------------------------------------------------------
    # Delivery helpers used by REST handlers
    # ------------------------------------------------------------------

    async def list_deliveries_for_webhook(
        self,
        db: AsyncSession,
        *,
        webhook_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[WebhookDelivery], int]:
        """Return ``(items, total)`` for paginated delivery listing."""
        total = await self._repository.count_deliveries(db, webhook_id)
        offset = (page - 1) * page_size
        items = await self._repository.list_deliveries(
            db, webhook_id, offset=offset, limit=page_size
        )
        return items, total

    async def get_delivery_for_webhook(
        self,
        db: AsyncSession,
        *,
        webhook_id: uuid.UUID,
        delivery_id: uuid.UUID,
    ) -> WebhookDelivery | None:
        """Return a delivery scoped to ``webhook_id`` or ``None``."""
        return await self._repository.find_delivery_for_webhook(db, webhook_id, delivery_id)

    async def create_test_delivery(
        self,
        db: AsyncSession,
        *,
        webhook: TenantWebhook,
        triggered_by: uuid.UUID,
    ) -> WebhookDelivery:
        """Create and enqueue a ``webhook.test`` delivery for ``webhook``.

        Generates a fresh envelope, persists the :class:`WebhookDelivery` row
        and dispatches the Celery task. The caller owns the transaction.
        """
        delivery_id = uuid.uuid4()
        envelope = build_envelope(
            event=WebhookEvent.WEBHOOK_TEST.value,
            tenant_id=webhook.tenant_id,
            data={"message": "Hello from auth", "triggered_by": str(triggered_by)},
            delivery_id=delivery_id,
        )
        delivery = WebhookDelivery(
            id=delivery_id,
            webhook_id=webhook.id,
            tenant_id=webhook.tenant_id,
            event=WebhookEvent.WEBHOOK_TEST.value,
            idempotency_key=secrets.token_hex(16),
            request_url=webhook.url,
            request_headers={},
            request_body=envelope,
            status=WebhookDeliveryStatus.PENDING,
            attempt=0,
            max_attempts=settings.webhook_max_attempts,
        )
        await self._repository.add(db, delivery)

        from auth.tasks.webhooks import deliver_webhook

        deliver_webhook.delay(str(delivery_id))
        return delivery

    async def replay_delivery(
        self,
        db: AsyncSession,
        *,
        webhook: TenantWebhook,
        original: WebhookDelivery,
    ) -> WebhookDelivery:
        """Clone ``original`` as a fresh delivery, persist and enqueue it.

        The replay keeps the source event and payload but receives a new ID
        and ``created_at`` timestamp; it starts at attempt 0 and respects the
        current ``max_attempts`` setting.
        """
        new_id = uuid.uuid4()
        envelope = dict(original.request_body)
        envelope["id"] = str(new_id)
        envelope["created_at"] = datetime.now(UTC).isoformat()

        replay = WebhookDelivery(
            id=new_id,
            webhook_id=webhook.id,
            tenant_id=webhook.tenant_id,
            event=original.event,
            idempotency_key=secrets.token_hex(16),
            request_url=webhook.url,
            request_headers={},
            request_body=envelope,
            status=WebhookDeliveryStatus.PENDING,
            attempt=0,
            max_attempts=settings.webhook_max_attempts,
        )
        await self._repository.add(db, replay)

        from auth.tasks.webhooks import deliver_webhook

        deliver_webhook.delay(str(new_id))
        return replay

    async def dispatch(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        event: str,
        data: dict[str, Any],
    ) -> list[uuid.UUID]:
        """Enqueue a delivery for each matching webhook.

        Persists ``WebhookDelivery`` rows (status=pending) inside the caller's
        transaction and schedules the Celery delivery task. The caller is
        responsible for committing. If no webhook matches, returns ``[]`` and
        performs no DB work.
        """
        webhooks = await self.find_matching_webhooks(db, tenant_id=tenant_id, event=event)
        if not webhooks:
            return []

        delivery_ids: list[uuid.UUID] = []
        for webhook in webhooks:
            try:
                validate_target_url(webhook.url)
            except WebhookURLError as e:
                logger.warning(
                    "Skipping webhook %s (tenant=%s, event=%s): %s",
                    webhook.id,
                    tenant_id,
                    event,
                    e,
                )
                continue

            delivery_id = uuid.uuid4()
            envelope = build_envelope(
                event=event,
                tenant_id=tenant_id,
                data=data,
                delivery_id=delivery_id,
            )
            delivery = WebhookDelivery(
                id=delivery_id,
                webhook_id=webhook.id,
                tenant_id=tenant_id,
                event=event,
                idempotency_key=secrets.token_hex(16),
                request_url=webhook.url,
                request_headers={},  # populated by the task on first attempt
                request_body=envelope,
                status=WebhookDeliveryStatus.PENDING,
                attempt=0,
                max_attempts=settings.webhook_max_attempts,
            )
            await self._repository.stage(db, delivery)
            delivery_ids.append(delivery_id)

        if not delivery_ids:
            return []

        await db.flush()

        # Import locally to avoid importing Celery at service import time
        # (keeps tests and non-worker contexts lightweight).
        from auth.tasks.webhooks import deliver_webhook

        for delivery_id in delivery_ids:
            deliver_webhook.delay(str(delivery_id))

        return delivery_ids


# Singleton
webhook_service = WebhookService()


async def safe_dispatch(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID | str | None,
    event: WebhookEvent | str,
    data: dict[str, Any],
) -> None:
    """Best-effort dispatch helper for use from services and shared routes.

    Shared across call sites that might not have a concrete tenant UUID
    (e.g. requests where the middleware could not resolve a tenant). Never
    raises — webhook issues must not break the originating business action.

    - Skips silently when ``tenant_id`` is None or not parseable as UUID.
    - Accepts ``event`` as a :class:`WebhookEvent` enum value or raw string.
    """
    if tenant_id is None:
        return
    if isinstance(tenant_id, str):
        try:
            tenant_uuid = uuid.UUID(tenant_id)
        except ValueError:
            return
    else:
        tenant_uuid = tenant_id

    event_value = event.value if hasattr(event, "value") else str(event)

    try:
        await webhook_service.dispatch(db, tenant_id=tenant_uuid, event=event_value, data=data)
    except Exception:  # noqa: BLE001 - isolation is the whole point
        logger.exception(
            "Failed to enqueue webhook dispatch (tenant=%s, event=%s)",
            tenant_uuid,
            event_value,
        )


def serialize_body(envelope: dict[str, Any]) -> bytes:
    """Canonical JSON encoding used both for signing and for transport."""
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
