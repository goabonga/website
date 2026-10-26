# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped organisation settings API endpoints."""

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

router = APIRouter(prefix="/settings", tags=["me-organisations:settings"])


@router.get("/", response_model=SettingsResponse)
async def get_settings(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> SettingsResponse:
    """Retrieve all settings for an organisation.

    Returns the full tenant settings object stored as a JSONB blob. The
    returned dictionary contains all keys that have been set on the tenant;
    an empty dict is returned when no settings have been configured yet.

    **Required scope:** org membership + `settings:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/settings/
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
    """Partially update settings for an organisation.

    Performs a shallow dict merge: only the keys supplied in the request body
    are written; all other existing keys in the JSONB settings blob are
    preserved. To remove a key, pass it explicitly with a `null` value.

    **Required scope:** org membership + `settings:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"settings": {"registration_fields": ["phone"], "email_sender": "noreply@acme.com"}}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/settings/
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
        "ACTION: me_settings_update, user_id=%s, org_id=%s, keys=%s",
        user.id,
        org_id,
        list(body.settings.keys()),
    )

    return SettingsResponse(settings=tenant.settings)
