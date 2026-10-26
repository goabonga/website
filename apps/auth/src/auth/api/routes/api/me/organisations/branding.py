# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped organisation branding API endpoints."""

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

router = APIRouter(prefix="/branding", tags=["me-organisations:branding"])


@router.get("/", response_model=BrandingResponse)
async def get_branding(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> BrandingResponse:
    """Retrieve the branding configuration for an organisation.

    Returns the current branding settings (colors, logos, fonts, custom CSS/JS)
    for the specified organisation. Raises 404 if no branding has been configured yet.

    **Required scope:** org membership + `branding:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/branding/
    ```
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

    Performs a full replacement of all branding fields (colors, logos, fonts,
    custom CSS/JS). If no branding record exists for the organisation it is
    created; otherwise the existing record is overwritten with the supplied values.

    **Required scope:** org membership + `branding:write`

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"primary_color": "#1a73e8", "logo_url": "https://cdn.example.com/logo.png"}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/branding/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="branding:write"
    )

    update_data = body.model_dump(exclude_unset=True)
    branding = await branding_service.save_branding(db, tenant.id, **update_data)

    await db.commit()
    await db.refresh(branding)

    logger.info(
        "ACTION: me_branding_update, user_id=%s, tenant_id=%s",
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
    """Delete the custom branding configuration for an organisation.

    Permanently removes all branding customisations for the organisation,
    reverting it to the platform default appearance. Returns 404 if no
    custom branding record exists.

    **Required scope:** org membership + `branding:write`

    **Responses:**
    - `204` — branding deleted successfully
    - `404` — no custom branding configured for this organisation

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/branding/
    ```
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
        "ACTION: me_branding_delete, user_id=%s, tenant_id=%s",
        user.id,
        tenant.id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
