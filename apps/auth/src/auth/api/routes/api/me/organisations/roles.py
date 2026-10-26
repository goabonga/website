# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped /me/organisations/{org_id}/roles endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    CreateRoleRequest,
    RoleResponse,
    UpdateRoleRequest,
)
from auth.db.models.user import User
from auth.services.tenant_role import tenant_role_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["me-organisation-roles"])


def _build_role_response(role) -> RoleResponse:
    """Build a RoleResponse from a TenantCustomRole model."""
    return RoleResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        scopes=role.scopes,
        is_system=role.is_system,
        is_default=role.is_default,
        display_order=role.display_order,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.get("/", response_model=list[RoleResponse])
async def list_roles(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> list[RoleResponse]:
    """List all roles for an organisation.

    Returns every custom and system role defined on the organisation's tenant,
    including their assigned scopes, display order, and whether the role is a
    system-managed default that cannot be deleted.

    **Required scope:** org membership + `roles:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/roles/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="roles:read"
    )

    roles = await tenant_role_service.get_tenant_roles(db, tenant.id)
    return [_build_role_response(r) for r in roles]


@router.post(
    "/",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_role(
    org_id: uuid.UUID,
    body: CreateRoleRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> RoleResponse:
    """Create a custom role for an organisation.

    Adds a new tenant-scoped RBAC role with the given name, display name, and
    set of allowed scopes. Scopes must be drawn from the tenant's permitted
    scope list; invalid or out-of-tenant scopes are rejected with `400`.

    **Required scope:** org membership + `roles:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "billing-viewer", "display_name": "Billing Viewer", "scopes": ["billing:read"], "description": "Read-only access to billing data"}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/roles/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="roles:write"
    )

    try:
        role = await tenant_role_service.create_role(
            db,
            tenant_id=tenant.id,
            name=body.name,
            display_name=body.display_name,
            scopes=body.scopes,
            description=body.description,
            tenant=tenant,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()

    logger.info(
        "ACTION: me_role_create, org_id=%s, user_id=%s, role_name=%s",
        tenant.id,
        user.id,
        role.name,
    )

    return _build_role_response(role)


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    body: UpdateRoleRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> RoleResponse:
    """Update a custom role in an organisation.

    Partially updates the display name, description, or scope list of an
    existing tenant role. System roles can have their display name and
    description changed but their scope list is immutable; attempting to
    alter system-role scopes returns `400`.

    **Required scope:** org membership + `roles:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"display_name": "Billing Admin", "scopes": ["billing:read", "billing:write"]}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/roles/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="roles:write"
    )

    role = await tenant_role_service.get_role_by_id(db, role_id)
    if not role or role.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    try:
        role = await tenant_role_service.update_role(
            db,
            role=role,
            display_name=body.display_name,
            scopes=body.scopes,
            description=body.description,
            tenant=tenant,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()

    logger.info(
        "ACTION: me_role_update, org_id=%s, user_id=%s, role_id=%s",
        tenant.id,
        user.id,
        role_id,
    )

    return _build_role_response(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> None:
    """Delete a custom role from an organisation.

    Permanently removes the tenant role. System roles and roles that are
    currently assigned to one or more organisation members cannot be deleted
    and will return `400`. Returns `204 No Content` on success.

    **Required scope:** org membership + `roles:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/roles/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="roles:delete"
    )

    role = await tenant_role_service.get_role_by_id(db, role_id)
    if not role or role.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    try:
        await tenant_role_service.delete_role(db, role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()

    logger.info(
        "ACTION: me_role_delete, org_id=%s, user_id=%s, role_id=%s",
        tenant.id,
        user.id,
        role_id,
    )
