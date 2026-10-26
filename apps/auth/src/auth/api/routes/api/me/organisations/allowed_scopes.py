# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped /me/organisations/{org_id}/allowed-scopes endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    AllowedScopesResponse,
    UpdateAllowedScopesRequest,
)
from auth.db.models.tenant import TENANT_SCOPES
from auth.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/allowed-scopes", tags=["me-organisations:allowed-scopes"])


@router.get("/", response_model=AllowedScopesResponse)
async def get_allowed_scopes(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> AllowedScopesResponse:
    """Return the allowed-scopes configuration for an organisation.

    Retrieves the list of OAuth2 scopes that are permitted for use within the
    organisation. When `allowed_scopes` is `null`, all tenant scopes are
    available without restriction.

    **Required scope:** org membership + `settings:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/allowed-scopes/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:read",
    )

    settings = tenant.settings or {}
    return AllowedScopesResponse(
        allowed_scopes=settings.get("allowed_scopes"),
    )


@router.patch("/", response_model=AllowedScopesResponse)
async def update_allowed_scopes(
    org_id: uuid.UUID,
    body: UpdateAllowedScopesRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> AllowedScopesResponse:
    """Update the allowed-scopes configuration for an organisation.

    Replaces the organisation's permitted scope list. Pass `null` for
    `allowed_scopes` to lift all restrictions and allow every tenant scope.
    Any scope name not present in the tenant's valid scope registry is rejected
    with `400`.

    **Required scope:** org membership + `settings:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"allowed_scopes": ["profile:read", "email:read"]}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/allowed-scopes/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:write",
    )

    # Validate scopes if provided (None means all allowed)
    if body.allowed_scopes is not None:
        valid_scopes = set(TENANT_SCOPES.keys())
        invalid = [s for s in body.allowed_scopes if s not in valid_scopes]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scopes: {', '.join(sorted(invalid))}",
            )

    current = dict(tenant.settings) if tenant.settings else {}
    current["allowed_scopes"] = body.allowed_scopes
    tenant.settings = current
    flag_modified(tenant, "settings")

    await db.flush()

    logger.info(
        "ACTION: me_allowed_scopes_update, user_id=%s, org_id=%s",
        user.id,
        org_id,
    )

    return AllowedScopesResponse(
        allowed_scopes=current["allowed_scopes"],
    )
