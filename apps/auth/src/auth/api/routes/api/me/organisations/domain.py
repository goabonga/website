# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped /me/organisations/{org_id}/domain endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.routes.api.organisations.domain import (
    build_domain_response,
    change_domain,
    verify_domain,
)
from auth.api.schemas.api.organisations import CustomDomainResponse, SetCustomDomainRequest
from auth.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domain", tags=["me-organisations:domain"])


@router.get("/", response_model=CustomDomainResponse)
async def get_custom_domain(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> CustomDomainResponse:
    """Get the custom domain of an organisation and the state of its verification.

    `status` is `null` without a domain, otherwise one of `pending`, `dns_verifying`,
    `dns_verified`, `ssl_provisioning`, `active` or `failed`.

    **Required scope:** org membership + `domain:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/domain/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="domain:read"
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

    The new domain starts in the `pending` state, a `tenant.updated` webhook event is
    dispatched and the DNS verification is queued. Returns `409` when another organisation
    uses the domain and `422` when it is not a well formed host name.

    **Required scope:** org membership + `domain:write`

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"custom_domain": "auth.acme.example"}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/domain/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="domain:write"
    )
    result = await change_domain(db, tenant, body.custom_domain, user)
    logger.info(
        "ACTION: me_custom_domain_set, user_id=%s, org_id=%s, domain=%s",
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

    Clears the verification state, dispatches a `tenant.updated` webhook event and queues the
    removal of the configuration of the domain.

    **Required scope:** org membership + `domain:write`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/domain/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="domain:write"
    )
    await change_domain(db, tenant, None, user)
    logger.info("ACTION: me_custom_domain_remove, user_id=%s, org_id=%s", user.id, org_id)


@router.post("/verify", response_model=CustomDomainResponse)
async def verify_custom_domain(
    org_id: uuid.UUID,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> CustomDomainResponse:
    """Ask for the DNS verification of the custom domain of an organisation.

    Returns `202` when the verification is queued, `200` when the domain is already active,
    `400` without a domain and `409` while a verification is running.

    **Required scope:** org membership + `domain:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/domain/verify
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="domain:write"
    )
    result = await verify_domain(db, tenant, user, response)
    logger.info("ACTION: me_custom_domain_verify, user_id=%s, org_id=%s", user.id, org_id)
    return result
