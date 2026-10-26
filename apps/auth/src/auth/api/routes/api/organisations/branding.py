# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Organisation branding API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_branding_service, get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    BrandingResponse,
    UpdateBrandingRequest,
)
from auth.db.models.user import User
from auth.services.branding import BrandingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/branding", tags=["organisations:branding"])


@router.get("/", response_model=BrandingResponse)
async def get_branding(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> BrandingResponse:
    """Return the branding configuration for an organisation.

    Retrieves the stored branding record (colours, logo URLs, fonts, and custom
    CSS/JS) for the given organisation. Returns 404 if no custom branding has
    been configured yet.

    **Required scope:** org membership + `branding:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/branding/
    ```

    **Responses:**
    - `200` — branding record returned
    - `403` — not a member of the organisation or missing `branding:read` scope
    - `404` — no branding configured for this organisation
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="branding:read"
    )

    branding = await branding_service.get_branding_record(db, tenant.id)
    if not branding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branding not configured for this organisation",
        )

    return BrandingResponse.model_validate(branding)


@router.put("/", response_model=BrandingResponse)
async def update_branding(
    org_id: uuid.UUID,
    body: UpdateBrandingRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> BrandingResponse:
    """Create or replace the branding configuration for an organisation.

    Performs a full upsert: if a branding record already exists it is updated
    with the supplied fields; otherwise a new record is created. All writable
    branding fields (colours, logo URLs, fonts, custom CSS/JS) may be set in a
    single request.

    **Required scope:** org membership + `branding:write`

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"primary_color": "#1a73e8", "logo_url": "https://cdn.example.com/logo.png"}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/branding/
    ```

    **Responses:**
    - `200` — branding record created or updated
    - `403` — not a member of the organisation or missing `branding:write` scope
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="branding:write"
    )

    update_data = body.model_dump(exclude_unset=True)
    branding = await branding_service.save_branding(db, tenant.id, **update_data)

    await db.commit()
    await db.refresh(branding)

    logger.info(
        "ACTION: branding_update, user_id=%s, tenant_id=%s",
        user.id,
        tenant.id,
    )

    return BrandingResponse.model_validate(branding)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branding(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Delete the custom branding for an organisation, reverting to defaults.

    Permanently removes the stored branding record so the organisation falls
    back to platform-default styling. Returns 404 if no custom branding exists.

    **Required scope:** org membership + `branding:write`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/branding/
    ```

    **Responses:**
    - `204` — branding deleted
    - `403` — not a member of the organisation or missing `branding:write` scope
    - `404` — no branding configured for this organisation
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="branding:write"
    )

    deleted = await branding_service.delete_branding(db, tenant.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branding not configured for this organisation",
        )

    await db.commit()

    logger.info(
        "ACTION: branding_delete, user_id=%s, tenant_id=%s",
        user.id,
        tenant.id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
