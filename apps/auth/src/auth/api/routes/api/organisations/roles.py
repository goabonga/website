# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations/{org_id}/roles endpoints."""

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

router = APIRouter(prefix="/roles", tags=["organisation-roles"])


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

    Returns both system-defined roles (read-only, shared across all tenants)
    and custom roles created specifically for this organisation. System roles
    cannot be modified or deleted.

    **Required scope:** org membership + `roles:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/roles/
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

    Defines a new RBAC role scoped to this tenant. The role's `scopes` list
    must be a subset of the scopes permitted for the organisation. System roles
    cannot be created via this endpoint — they are provisioned automatically.

    **Required scope:** org membership + `roles:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "billing-admin", "display_name": "Billing Admin", "scopes": ["billing:read", "billing:write"], "description": "Manages billing settings"}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/roles/
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
        "ACTION: role_create, org_id=%s, user_id=%s, role_name=%s",
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

    Partially updates a custom role's display name, description, scopes, or
    default-role flag. Setting `is_default` to `true` atomically clears the
    previous default role for the tenant. System roles cannot be updated.

    **Required scope:** org membership + `roles:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"display_name": "Senior Billing Admin", "scopes": ["billing:read", "billing:write", "billing:export"], "is_default": false}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/roles/6ba7b810-9dad-11d1-80b4-00c04fd430c8
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

    # Apply is_default transition after scope/name updates so we have the
    # final authoritative scopes to reason about. set_default_role clears
    # any previously-default role in the same tenant before flipping.
    if body.is_default is not None:
        if body.is_default and not role.is_default:
            await tenant_role_service.set_default_role(db, tenant.id, role.id)
        elif not body.is_default and role.is_default:
            await tenant_role_service.clear_default_role(db, tenant.id)

    await db.commit()

    logger.info(
        "ACTION: role_update, org_id=%s, user_id=%s, role_id=%s, is_default=%s",
        tenant.id,
        user.id,
        role_id,
        role.is_default,
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

    Permanently removes a custom role from the tenant. Deletion fails if the
    role is a system role or is currently assigned to one or more members.

    **Required scope:** org membership + `roles:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/roles/6ba7b810-9dad-11d1-80b4-00c04fd430c8
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
        "ACTION: role_delete, org_id=%s, user_id=%s, role_id=%s",
        tenant.id,
        user.id,
        role_id,
    )
