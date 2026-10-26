# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations/{org_id}/settings endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    SettingsResponse,
    UpdateSettingsRequest,
)
from auth.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["organisations-settings"])


@router.get("/", response_model=SettingsResponse)
async def get_settings(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> SettingsResponse:
    """Return all JSONB settings for an organisation.

    Retrieves the full `settings` JSONB object stored on the tenant record.
    The object is returned as-is; keys depend on the tenant's configuration
    (e.g. `registration_fields`, `profile_fields`, `allowed_scopes`).

    **Required scope:** org membership + `settings:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/settings/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:read",
    )

    return SettingsResponse(settings=tenant.settings or {})


@router.patch("/", response_model=SettingsResponse)
async def update_settings(
    org_id: uuid.UUID,
    body: UpdateSettingsRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> SettingsResponse:
    """Partially update JSONB settings for an organisation using shallow merge.

    Performs a shallow merge of the incoming `settings` dict into the existing
    tenant settings: top-level keys in the request body are added or overwritten,
    while keys absent from the request body are preserved unchanged. To remove a
    key, pass it explicitly with a `null` value.

    **Required scope:** org membership + `settings:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"settings": {"registration_fields": ["email", "display_name"], "allowed_scopes": ["profile:read"]}}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/settings/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:write",
    )

    # Merge: existing settings + incoming keys
    current = dict(tenant.settings) if tenant.settings else {}
    current.update(body.settings)
    tenant.settings = current

    await db.flush()

    logger.info(
        "ACTION: settings_update, user_id=%s, org_id=%s, keys=%s",
        user.id,
        org_id,
        list(body.settings.keys()),
    )

    return SettingsResponse(settings=tenant.settings)
