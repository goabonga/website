# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations/{org_id}/registration-fields endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    RegistrationFieldsResponse,
    UpdateRegistrationFieldsRequest,
)
from auth.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/registration-fields", tags=["organisations-registration-fields"])

REGISTRATION_FIELD_KEYS = [
    "profile",
    "nickname",
    "firstname",
    "lastname",
    "middle_name",
    "preferred_username",
    "personal_details",
    "gender",
    "birthdate",
    "locale",
    "zoneinfo",
    "phone_number",
    "address",
    "picture",
    "web_presence",
]

_VALID_KEYS = frozenset(REGISTRATION_FIELD_KEYS)


def _build_fields(tenant_settings: dict | None) -> dict[str, bool]:
    """Merge stored overrides with defaults (all True)."""
    fields: dict[str, bool] = dict.fromkeys(REGISTRATION_FIELD_KEYS, True)
    overrides = (tenant_settings or {}).get("registration_fields", {})
    for key in fields:
        if key in overrides:
            fields[key] = bool(overrides[key])
    return fields


@router.get("/", response_model=RegistrationFieldsResponse)
async def get_registration_fields(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> RegistrationFieldsResponse:
    """Get registration field visibility toggles for an organisation.

    Returns a map of all known registration fields to their enabled/disabled
    state. Fields default to `true` (visible at sign-up) unless explicitly
    overridden in the tenant settings.

    **Required scope:** org membership + `settings:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/registration-fields/
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
    return RegistrationFieldsResponse(fields=fields)


@router.patch("/", response_model=RegistrationFieldsResponse)
async def update_registration_fields(
    org_id: uuid.UUID,
    body: UpdateRegistrationFieldsRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> RegistrationFieldsResponse:
    """Update registration field visibility toggles for an organisation.

    Partially merges the provided field map into the tenant's settings. Only
    the keys present in the request body are changed; omitted fields keep their
    current value. Unknown field keys are rejected with a `400` error.

    **Required scope:** org membership + `settings:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"fields": {"birthdate": false, "phone_number": true}}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/registration-fields/
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
            detail=f"Unknown registration field keys: {sorted(unknown)}",
        )

    # Merge into settings JSONB
    current = dict(tenant.settings) if tenant.settings else {}
    existing_fields = current.get("registration_fields", {})
    existing_fields.update(body.fields)
    current["registration_fields"] = existing_fields
    tenant.settings = current
    flag_modified(tenant, "settings")

    await db.flush()

    logger.info(
        "ACTION: registration_fields_update, user_id=%s, org_id=%s, keys=%s",
        user.id,
        org_id,
        list(body.fields.keys()),
    )

    fields = _build_fields(tenant.settings)
    return RegistrationFieldsResponse(fields=fields)
