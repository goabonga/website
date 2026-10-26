# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations CRUD endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.api.deps import get_db, token_has_scope
from auth.api.routes.api.deps import (
    get_current_user_bearer,
    require_admin_scope,
)
from auth.api.schemas.api.common import PaginatedResponse
from auth.api.schemas.api.organisations import (
    CreateOrganisationAdminRequest,
    OrganisationResponse,
    UpdateOrganisationRequest,
)
from auth.db.models.tenant import Tenant, TenantMember
from auth.db.models.user import User
from auth.services.tenant import TenantService
from auth.services.tenant_role import tenant_role_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organisations", tags=["organisations"])

_tenant_service = TenantService()


async def _build_org_response(db: AsyncSession, tenant: Tenant) -> OrganisationResponse:
    """Build an OrganisationResponse from a Tenant model."""
    member_count = await _tenant_service.count_members(db, tenant.id)
    return OrganisationResponse(
        id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        custom_domain=tenant.custom_domain,
        is_active=tenant.is_active,
        trust_mode=tenant.trust_mode.value if tenant.trust_mode else "none",
        member_count=member_count,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


@router.get("/", response_model=PaginatedResponse[OrganisationResponse])
async def list_organisations(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("org:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[OrganisationResponse]:
    """List all organisations with pagination.

    Returns a paginated list of all organisations across all tenants. Results
    are ordered by creation date descending. Each item includes the live
    member count.

    **Required scope:** `org:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/organisations/?page=1&page_size=20"
    ```
    """
    tenants, total = await _tenant_service.list_tenants(db, page=page, page_size=page_size)
    items = [await _build_org_response(db, t) for t in tenants]

    return PaginatedResponse[OrganisationResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/",
    response_model=OrganisationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organisation(
    body: CreateOrganisationAdminRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("org:write"))],
) -> OrganisationResponse:
    """Create a new organisation.

    Provisions a new tenant with the given slug and display name. The slug must
    be unique across all tenants and cannot be changed after creation. Default
    RBAC roles are automatically created for the new organisation.

    **Required scope:** `org:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"slug": "acme-corp", "display_name": "Acme Corp"}' \\
      https://auth.example.com/api/v1/organisations/
    ```

    **Responses:**
    - `201` — organisation created
    - `409` — slug already in use
    """
    try:
        tenant = await _tenant_service.create_tenant(
            db,
            slug=body.slug,
            display_name=body.display_name,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organisation with this slug already exists",
        )

    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "ACTION: organisation_create_admin, user_id=%s, tenant_id=%s, slug=%s",
        user.id,
        tenant.id,
        tenant.slug,
    )

    return await _build_org_response(db, tenant)


@router.get("/{org_id}", response_model=OrganisationResponse)
async def get_organisation(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> OrganisationResponse:
    """Retrieve a single organisation by ID.

    Tokens with the `org:read` scope can read any organisation regardless of
    membership. Tokens without that scope are restricted to organisations where
    the authenticated user is an active member; inactive organisations are not
    visible to non-admin callers.

    **Required scope:** `org:read` (admin) or org membership

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000
    ```

    **Responses:**
    - `200` — organisation found
    - `403` — caller is not a member of the organisation
    - `404` — organisation not found
    """
    scopes = getattr(request.state, "auth_scopes", [])
    is_admin = token_has_scope(scopes, "org:read")

    if is_admin:
        # Admin can read any org
        tenant = await _tenant_service.get_by_id(db, org_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organisation not found",
            )
    else:
        # Non-admin: must be a member of an active org
        tenant = await _tenant_service.get_active_by_id(db, org_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organisation not found",
            )

        if not await _tenant_service.get_member(db, org_id, user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this organisation",
            )

    return await _build_org_response(db, tenant)


@router.patch("/{org_id}", response_model=OrganisationResponse)
async def update_organisation(
    org_id: uuid.UUID,
    body: UpdateOrganisationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> OrganisationResponse:
    """Partially update an organisation's attributes.

    Tokens with the `org:write` scope can update any organisation. Tokens
    without that scope are accepted only if the authenticated user holds the
    owner role inside the target organisation. All fields are optional; only
    provided fields are modified.

    **Required scope:** `org:write` (admin) or org owner role

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"display_name": "Acme Corp (updated)"}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000
    ```

    **Responses:**
    - `200` — organisation updated
    - `403` — caller is not an admin or org owner
    - `404` — organisation not found
    """
    scopes = getattr(request.state, "auth_scopes", [])
    is_admin = token_has_scope(scopes, "org:write")

    tenant = await _tenant_service.get_by_id(db, org_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    if not is_admin:
        # Check org owner (need custom_role eager-loaded for is_owner check)
        membership = await _tenant_service.get_member(db, org_id, user.id)
        # Ensure custom_role is loaded — get_member already eager-loads it
        _ = selectinload  # retain for potential future typed checks
        if not membership or not tenant_role_service.is_owner(membership):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing required permission: org:write",
            )

    await _tenant_service.update_tenant(
        db,
        tenant,
        display_name=body.display_name,
        is_active=body.is_active,
    )
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "ACTION: organisation_update, user_id=%s, tenant_id=%s",
        user.id,
        tenant.id,
    )

    return await _build_org_response(db, tenant)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organisation(
    org_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("org:delete"))],
) -> None:
    """Permanently delete an organisation.

    Removes the organisation and all its associated data. The platform tenant
    is protected and cannot be deleted; attempting to do so returns `400`.
    This action is irreversible.

    **Required scope:** `org:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000
    ```

    **Responses:**
    - `204` — organisation deleted
    - `400` — cannot delete the platform tenant
    - `404` — organisation not found
    """
    tenant = await _tenant_service.get_by_id(db, org_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    if tenant.is_platform:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the platform tenant",
        )

    await _tenant_service.delete_tenant(db, tenant)
    await db.commit()

    logger.info(
        "ACTION: organisation_delete, user_id=%s, tenant_id=%s, slug=%s",
        user.id,
        tenant.id,
        tenant.slug,
    )


@router.post("/{org_id}/enable", response_model=OrganisationResponse)
async def enable_organisation(
    org_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("org:write"))],
) -> OrganisationResponse:
    """Enable a previously disabled organisation.

    Sets `is_active` to `true`, allowing the organisation's members to
    authenticate and use the platform again. Has no effect if the organisation
    is already active.

    **Required scope:** `org:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/enable
    ```

    **Responses:**
    - `200` — organisation enabled, updated record returned
    - `404` — organisation not found
    """
    tenant = await _tenant_service.get_by_id(db, org_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    await _tenant_service.set_active(db, tenant, active=True)
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "ACTION: organisation_enable, user_id=%s, tenant_id=%s, slug=%s",
        user.id,
        tenant.id,
        tenant.slug,
    )

    return await _build_org_response(db, tenant)


@router.post("/{org_id}/disable", response_model=OrganisationResponse)
async def disable_organisation(
    org_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("org:write"))],
) -> OrganisationResponse:
    """Disable an active organisation.

    Sets `is_active` to `false`, preventing members from authenticating under
    this organisation. The platform tenant is protected and cannot be disabled;
    attempting to do so returns `400`. Use the `/enable` endpoint to reverse.

    **Required scope:** `org:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/disable
    ```

    **Responses:**
    - `200` — organisation disabled, updated record returned
    - `400` — cannot disable the platform tenant
    - `404` — organisation not found
    """
    tenant = await _tenant_service.get_by_id(db, org_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    if tenant.is_platform:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable the platform tenant",
        )

    await _tenant_service.set_active(db, tenant, active=False)
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "ACTION: organisation_disable, user_id=%s, tenant_id=%s, slug=%s",
        user.id,
        tenant.id,
        tenant.slug,
    )

    return await _build_org_response(db, tenant)


# Keep a reference to TenantMember for backwards compatibility if imported.
_ = TenantMember

# ---------------------------------------------------------------------------
# Sub-resource routers
# ---------------------------------------------------------------------------
from auth.api.routes.api.organisations.allowed_scopes import (  # noqa: E402
    router as allowed_scopes_router,
)
from auth.api.routes.api.organisations.branding import router as branding_router  # noqa: E402
from auth.api.routes.api.organisations.clients import router as clients_router  # noqa: E402
from auth.api.routes.api.organisations.email_sender import (  # noqa: E402
    router as email_sender_router,
)
from auth.api.routes.api.organisations.idps import router as idps_router  # noqa: E402
from auth.api.routes.api.organisations.members import router as members_router  # noqa: E402
from auth.api.routes.api.organisations.profile_fields import (  # noqa: E402
    router as profile_fields_router,
)
from auth.api.routes.api.organisations.registration_fields import (  # noqa: E402
    router as registration_fields_router,
)
from auth.api.routes.api.organisations.roles import router as roles_router  # noqa: E402
from auth.api.routes.api.organisations.settings import router as settings_router  # noqa: E402
from auth.api.routes.api.organisations.templates import router as templates_router  # noqa: E402
from auth.api.routes.api.organisations.trust import router as trust_router  # noqa: E402
from auth.api.routes.api.organisations.webhooks import router as webhooks_router  # noqa: E402

router.include_router(members_router, prefix="/{org_id}")
router.include_router(roles_router, prefix="/{org_id}")
router.include_router(clients_router, prefix="/{org_id}")
router.include_router(idps_router, prefix="/{org_id}")
router.include_router(branding_router, prefix="/{org_id}")
router.include_router(templates_router, prefix="/{org_id}")
router.include_router(trust_router, prefix="/{org_id}")
router.include_router(settings_router, prefix="/{org_id}")
router.include_router(registration_fields_router, prefix="/{org_id}")
router.include_router(profile_fields_router, prefix="/{org_id}")
router.include_router(email_sender_router, prefix="/{org_id}")
router.include_router(allowed_scopes_router, prefix="/{org_id}")
router.include_router(webhooks_router, prefix="/{org_id}")
