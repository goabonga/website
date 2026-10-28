# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations/{org_id}/domain endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import CustomDomainResponse, SetCustomDomainRequest
from auth.db.models.tenant import Tenant
from auth.db.models.user import User
from auth.services.custom_domain import (
    VerificationOutcome,
    custom_domain_service,
    is_valid_domain,
)
from auth.services.tenant import tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domain", tags=["organisations-domain"])


def build_domain_response(tenant: Tenant) -> CustomDomainResponse:
    """The custom domain of ``tenant`` and the state of its verification."""
    return CustomDomainResponse(**custom_domain_service.status(tenant))


async def change_domain(
    db: AsyncSession, tenant: Tenant, domain: str | None, user: User
) -> CustomDomainResponse:
    """Set (a host name) or remove (``None``) the custom domain of ``tenant``.

    Shared by the ``/organisations`` and ``/me/organisations`` routes.

    Raises:
        HTTPException 422: ``domain`` is not a well formed host name.
        HTTPException 409: Another organisation already uses ``domain``.
    """
    if domain is not None:
        domain = domain.strip().lower()
        if not is_valid_domain(domain):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid domain name",
            )
        holder = await tenant_service.get_by_custom_domain(db, domain)
        if holder is not None and holder.id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This domain is already used by another organisation",
            )
    await custom_domain_service.set_domain(db, tenant, domain, actor_id=user.id)
    return build_domain_response(tenant)


async def verify_domain(
    db: AsyncSession, tenant: Tenant, user: User, response: Response
) -> CustomDomainResponse:
    """Ask for the DNS verification of the custom domain of ``tenant``.

    Answers ``202`` when the verification is queued and ``200`` when the domain is already
    active.

    Raises:
        HTTPException 400: The organisation has no custom domain.
        HTTPException 409: A verification is already in progress.
    """
    outcome = await custom_domain_service.start_verification(db, tenant, actor_id=user.id)
    if outcome is VerificationOutcome.NO_DOMAIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No custom domain configured",
        )
    if outcome is VerificationOutcome.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Domain verification already in progress",
        )
    if outcome is VerificationOutcome.STARTED:
        response.status_code = status.HTTP_202_ACCEPTED
    return build_domain_response(tenant)


@router.get("/", response_model=CustomDomainResponse)
async def get_custom_domain(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> CustomDomainResponse:
    """Return the custom domain of an organisation and the state of its verification.

    `status` is one of `pending`, `dns_verifying`, `dns_verified`, `ssl_provisioning`,
    `active` or `failed` (`null` without a domain). Poll it after setting the domain.

    **Required scope:** org membership + `domain:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/domain/
    ```

    **Responses:**
    - `200` — the domain and its state
    - `403` — caller is not a member or lacks `domain:read`
    - `404` — organisation not found
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="domain:read",
    )
    return build_domain_response(tenant)


@router.put("/", response_model=CustomDomainResponse)
async def set_custom_domain(
    org_id: uuid.UUID,
    body: SetCustomDomainRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> CustomDomainResponse:
    """Set or change the custom domain of an organisation.

    A new domain starts in the `pending` state, a `tenant.updated` webhook event is
    dispatched and the DNS verification is queued (the domain must be a CNAME to the
    target of the platform). Setting the current domain again changes nothing.

    **Required scope:** org membership + `domain:write`

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"custom_domain": "auth.acme.example"}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/domain/
    ```

    **Responses:**
    - `200` — domain set, its state returned
    - `403` — caller is not a member or lacks `domain:write`
    - `404` — organisation not found
    - `409` — another organisation uses this domain
    - `422` — not a well formed host name
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="domain:write",
    )
    result = await change_domain(db, tenant, body.custom_domain, user)
    logger.info(
        "ACTION: custom_domain_set, user_id=%s, org_id=%s, domain=%s",
        user.id,
        org_id,
        result.custom_domain,
    )
    return result


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def remove_custom_domain(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> None:
    """Remove the custom domain of an organisation.

    Clears the verification state, dispatches a `tenant.updated` webhook event and queues
    the removal of the configuration of the domain. Removing a domain that is not set changes
    nothing.

    **Required scope:** org membership + `domain:write`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/domain/
    ```

    **Responses:**
    - `204` — no custom domain any more
    - `403` — caller is not a member or lacks `domain:write`
    - `404` — organisation not found
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="domain:write",
    )
    await change_domain(db, tenant, None, user)
    logger.info("ACTION: custom_domain_remove, user_id=%s, org_id=%s", user.id, org_id)


@router.post("/verify", response_model=CustomDomainResponse)
async def verify_custom_domain(
    org_id: uuid.UUID,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> CustomDomainResponse:
    """Ask for the DNS verification of the custom domain of an organisation.

    Resets the state to `pending` and queues the verification; poll the state with
    `GET .../domain/`. A domain that is already `active` is returned as it is.

    **Required scope:** org membership + `domain:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/domain/verify
    ```

    **Responses:**
    - `202` — verification queued
    - `200` — the domain is already active
    - `400` — the organisation has no custom domain
    - `403` — caller is not a member or lacks `domain:write`
    - `404` — organisation not found
    - `409` — a verification or the SSL provisioning is already in progress
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="domain:write",
    )
    result = await verify_domain(db, tenant, user, response)
    logger.info("ACTION: custom_domain_verify, user_id=%s, org_id=%s", user.id, org_id)
    return result
