# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations/{org_id}/profile-fields endpoints."""

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

router = APIRouter(prefix="/profile-fields", tags=["organisations-profile-fields"])

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
    """Return the profile field visibility toggles for an organisation.

    Each toggle controls whether the corresponding user profile field is
    editable by members of the tenant. Fields default to enabled (`true`) when
    no override has been stored for the organisation.

    **Required scope:** org membership + `settings:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/profile-fields/
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
    """Partially update profile field visibility toggles for an organisation.

    Accepts a map of field keys to boolean values and merges them into the
    organisation's stored settings. Only the keys present in the request body
    are modified; omitted keys retain their current state. Unknown field keys
    are rejected with `400`.

    **Required scope:** org membership + `settings:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"fields": {"nickname": false, "birthdate": false}}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/profile-fields/
    ```
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
        "ACTION: profile_fields_update, user_id=%s, org_id=%s, keys=%s",
        user.id,
        org_id,
        list(body.fields.keys()),
    )

    fields = _build_fields(tenant.settings)
    return ProfileFieldsResponse(fields=fields)
