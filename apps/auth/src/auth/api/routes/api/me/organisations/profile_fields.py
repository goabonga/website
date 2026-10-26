# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped /me/organisations/{org_id}/profile-fields endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    ProfileFieldsResponse,
    UpdateProfileFieldsRequest,
)
from auth.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile-fields", tags=["me-organisations:profile-fields"])

PROFILE_FIELD_KEYS = [
    "avatar",
    "identity",
    "nickname",
    "preferred_username",
    "given_name",
    "middle_name",
    "family_name",
    "personal_info",
    "gender",
    "birthdate",
    "locale",
    "zoneinfo",
    "contact",
    "phone_number",
    "website",
    "profile_url",
    "picture_url",
    "address",
    "roles_permissions",
]

_VALID_KEYS = frozenset(PROFILE_FIELD_KEYS)


def _build_fields(tenant_settings: dict | None) -> dict[str, bool]:
    """Merge stored overrides with defaults (all True)."""
    fields: dict[str, bool] = dict.fromkeys(PROFILE_FIELD_KEYS, True)
    overrides = (tenant_settings or {}).get("profile_fields", {})
    for key in fields:
        if key in overrides:
            fields[key] = bool(overrides[key])
    return fields


@router.get("/", response_model=ProfileFieldsResponse)
async def get_profile_fields(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> ProfileFieldsResponse:
    """Return the profile field visibility configuration for the organisation.

    Each field key maps to a boolean indicating whether that profile field is
    editable by members of the organisation. Fields not explicitly overridden
    in tenant settings default to `true` (visible/editable).

    **Required scope:** org membership + `settings:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/profile-fields/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:read",
    )

    fields = _build_fields(tenant.settings)
    return ProfileFieldsResponse(fields=fields)


@router.patch("/", response_model=ProfileFieldsResponse)
async def update_profile_fields(
    org_id: uuid.UUID,
    body: UpdateProfileFieldsRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> ProfileFieldsResponse:
    """Update profile field visibility settings for the organisation.

    Accepts a partial map of field keys to booleans and merges them into the
    existing tenant settings. Only known field keys are accepted; unknown keys
    cause a `400` error. Unspecified fields retain their current value.

    **Required scope:** org membership + `settings:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"fields": {"nickname": false, "birthdate": true}}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/profile-fields/
    ```

    **Responses:**
    - `200` — updated field map returned
    - `400` — unknown profile field key(s) supplied
    - `403` — missing required scope or not an org member
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:write",
    )

    # Validate keys
    unknown = set(body.fields.keys()) - _VALID_KEYS
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown profile field keys: {sorted(unknown)}",
        )

    # Merge into settings JSONB
    current = dict(tenant.settings) if tenant.settings else {}
    existing_fields = current.get("profile_fields", {})
    existing_fields.update(body.fields)
    current["profile_fields"] = existing_fields
    tenant.settings = current
    flag_modified(tenant, "settings")

    await db.flush()

    logger.info(
        "ACTION: me_profile_fields_update, user_id=%s, org_id=%s, keys=%s",
        user.id,
        org_id,
        list(body.fields.keys()),
    )

    fields = _build_fields(tenant.settings)
    return ProfileFieldsResponse(fields=fields)
