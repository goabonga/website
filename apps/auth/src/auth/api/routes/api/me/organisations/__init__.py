# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User organisations API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer
from auth.api.routes.api.me.organisations import (
    allowed_scopes,
    branding,
    clients,
    domain,
    email_sender,
    idps,
    members,
    profile_fields,
    registration_fields,
    roles,
    settings,
    templates,
    trust,
)
from auth.api.schemas.api.me import (
    CreateOrganisationRequest,
    OrganisationSummaryResponse,
)
from auth.db.models.user import User
from auth.services.tenant import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organisations", tags=["me-organisations"])

_tenant_service = TenantService()


@router.get("/", response_model=list[OrganisationSummaryResponse])
async def list_my_organisations(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> list[OrganisationSummaryResponse]:
    """List all organisations the current user belongs to.

    Returns a summary of every active organisation in which the authenticated
    user holds a membership, including their assigned role within each org.
    Inactive organisations are excluded from the result.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/
    ```
    """
    memberships = await _tenant_service.list_user_memberships(db, user.id)

    return [
        OrganisationSummaryResponse(
            id=m.tenant.id,
            slug=m.tenant.slug,
            display_name=m.tenant.display_name,
            role_name=m.role_name,
            role_display_name=m.role_display_name,
            joined_at=m.joined_at,
        )
        for m in memberships
        if m.tenant.is_active
    ]


@router.post(
    "/",
    response_model=OrganisationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organisation(
    body: CreateOrganisationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> OrganisationSummaryResponse:
    """Create a new organisation and assign the current user as owner.

    Provisions a new tenant with the given slug and display name, seeds it with
    default roles, and automatically enrolls the authenticated user as the
    organisation owner. Returns a conflict error if the slug is already taken.

    **Required scope:** any valid Bearer token

    **Responses:**
    - `201` — organisation created, user enrolled as owner
    - `409` — a organisation with this slug already exists

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"slug": "acme-corp", "display_name": "Acme Corp"}' \\
      https://auth.example.com/api/v1/me/organisations/
    ```
    """
    try:
        tenant, member = await _tenant_service.create_organisation_with_owner(
            db,
            slug=body.slug,
            display_name=body.display_name,
            owner_user_id=user.id,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organisation with this slug already exists",
        ) from None

    await db.commit()

    logger.info(
        "ACTION: organisation_create_api_v1, user_id=%s, tenant_id=%s, slug=%s",
        user.id,
        tenant.id,
        tenant.slug,
    )

    return OrganisationSummaryResponse(
        id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        role_name=member.role_name,
        role_display_name=member.role_display_name,
        joined_at=member.joined_at,
    )


router.include_router(members.router, prefix="/{org_id}")
router.include_router(roles.router, prefix="/{org_id}")
router.include_router(branding.router, prefix="/{org_id}")
router.include_router(templates.router, prefix="/{org_id}")
router.include_router(trust.router, prefix="/{org_id}")
router.include_router(settings.router, prefix="/{org_id}")
router.include_router(clients.router, prefix="/{org_id}")
router.include_router(idps.router, prefix="/{org_id}")
router.include_router(registration_fields.router, prefix="/{org_id}")
router.include_router(profile_fields.router, prefix="/{org_id}")
router.include_router(email_sender.router, prefix="/{org_id}")
router.include_router(allowed_scopes.router, prefix="/{org_id}")
router.include_router(domain.router, prefix="/{org_id}")
