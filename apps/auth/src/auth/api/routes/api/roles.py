# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /roles admin endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import require_admin_scope
from auth.api.schemas.api.common import MessageResponse, PaginatedResponse
from auth.api.schemas.api.roles import (
    AssignRoleRequest,
    CreateRoleRequest,
    RoleResponse,
    SeedRolesResponse,
    UpdateRoleRequest,
)
from auth.db.models.rbac import Role
from auth.db.models.user import User
from auth.services.role import RoleService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["roles"])

_role_service = RoleService()
_user_service = UserService()


def _build_role_response(role: Role) -> RoleResponse:
    """Build a RoleResponse from a Role model with loaded role_scopes."""
    scope_names = role.get_all_scope_names()
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        scopes=scope_names,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.get("/", response_model=PaginatedResponse[RoleResponse])
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[RoleResponse]:
    """List all roles with their assigned scopes.

    Returns a paginated list of all roles defined in the system, including
    both system roles and custom roles, each with their full scope list.

    **Required scope:** `roles:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/roles/?page=1&page_size=20"
    ```
    """
    roles, total = await _role_service.list(db, page=page, page_size=page_size)

    items = [_build_role_response(r) for r in roles]

    return PaginatedResponse[RoleResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: CreateRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:write"))],
) -> RoleResponse:
    """Create a new custom role and optionally attach scopes.

    System roles cannot be created via this endpoint; use the seed endpoint
    instead. Returns `409` if a role with the same name already exists.
    Scope IDs that do not exist will result in a `400` error.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "editor", "description": "Can edit content", "scope_ids": []}' \\
      https://auth.example.com/api/v1/roles/
    ```
    """
    try:
        role = await _role_service.create_role(
            db,
            name=body.name,
            description=body.description,
            scope_ids=body.scope_ids,
        )
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc

    reloaded = await _role_service.get_by_id(db, role.id, load_scopes=True)
    assert reloaded is not None  # just created
    return _build_role_response(reloaded)


@router.post("/seed", response_model=SeedRolesResponse, status_code=status.HTTP_200_OK)
async def seed_default_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:write"))],
) -> SeedRolesResponse:
    """Seed the default system roles defined in the application codebase.

    Iterates over the built-in `DEFAULT_ROLES` map and creates any roles that
    are not yet present in the database, assigning their predefined scopes.
    Already-existing roles are silently skipped; the operation is idempotent.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/roles/seed
    ```
    """
    created = await _role_service.seed_default_roles(db)

    logger.info(
        "ACTION: admin_roles_seed, admin_id=%s, created=%s",
        user.id,
        ", ".join(created) or "none",
    )

    return SeedRolesResponse(
        message=f"Created {len(created)} role(s)",
        created_roles=created,
    )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:read"))],
) -> RoleResponse:
    """Get a single role by ID, including all assigned scopes.

    Returns `404` if no role with the given ID exists.

    **Required scope:** `roles:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/roles/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    role = await _role_service.get_by_id(db, role_id, load_scopes=True)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    return _build_role_response(role)


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: uuid.UUID,
    body: UpdateRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:write"))],
) -> RoleResponse:
    """Update a role's name, description, or assigned scopes.

    All fields are optional; only provided fields are changed. If `scope_ids`
    is supplied the existing scope assignments are fully replaced with the new
    set. Returns `404` if the role does not exist and `409` if the new name
    conflicts with an existing role.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"description": "Updated description", "scope_ids": ["6ba7b810-9dad-11d1-80b4-00c04fd430c8"]}' \\
      https://auth.example.com/api/v1/roles/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    role = await _role_service.get_by_id(db, role_id, load_scopes=True)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    try:
        await _role_service.update_role(
            db,
            role,
            name=body.name,
            description=body.description,
            scope_ids=body.scope_ids,
        )
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc

    reloaded = await _role_service.get_by_id(db, role_id, load_scopes=True)
    assert reloaded is not None
    return _build_role_response(reloaded)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:delete"))],
) -> None:
    """Delete a custom role by ID.

    System roles (where `is_system` is `true`) cannot be deleted and will
    return `400`. Returns `404` if the role does not exist. On success
    returns `204 No Content`.

    **Required scope:** `roles:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/roles/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    role = await _role_service.get_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    try:
        await _role_service.delete_role(db, role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{role_id}/users",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_role_to_user(
    role_id: uuid.UUID,
    body: AssignRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:assign"))],
) -> MessageResponse:
    """Assign a role to a user by user ID.

    Returns `404` if either the role or target user does not exist. Returns
    `409` if the user already holds the specified role.

    **Required scope:** `roles:assign`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"user_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"}' \\
      https://auth.example.com/api/v1/roles/550e8400-e29b-41d4-a716-446655440000/users
    ```
    """
    role = await _role_service.get_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    target = await _user_service.get_by_id(db, body.user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        await _role_service.assign_role_to_user(
            db,
            role_id=role_id,
            user_id=body.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    logger.info(
        "ACTION: admin_role_assign, admin_id=%s, role_id=%s, target_user_id=%s",
        user.id,
        role_id,
        body.user_id,
    )

    return MessageResponse(message=f"Role '{role.name}' assigned to user {body.user_id}")


@router.delete(
    "/{role_id}/users/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_role_from_user(
    role_id: uuid.UUID,
    target_user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:assign"))],
) -> None:
    """Remove a role assignment from a user.

    Returns `404` if the specified role-to-user assignment does not exist.
    On success returns `204 No Content`.

    **Required scope:** `roles:assign`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/roles/550e8400-e29b-41d4-a716-446655440000/users/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```
    """
    user_role = await _role_service.get_user_role(db, role_id, target_user_id)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role assignment not found",
        )

    await _role_service.remove_role_from_user(db, user_role)

    logger.info(
        "ACTION: admin_role_unassign, admin_id=%s, role_id=%s, target_user_id=%s",
        user.id,
        role_id,
        target_user_id,
    )


@router.post(
    "/{role_id}/scopes/{scope_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_scope_to_role(
    role_id: uuid.UUID,
    scope_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:write"))],
) -> MessageResponse:
    """Assign a scope to a role by scope ID.

    Returns `404` if the role or scope does not exist. Returns `409` if the
    role already has the specified scope assigned.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/roles/550e8400-e29b-41d4-a716-446655440000/scopes/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```
    """
    role = await _role_service.get_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    # TODO: delegate to ScopeService once the scopes refactor lands.
    scope = await _role_service._get_scope_by_id(db, scope_id)
    if not scope:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scope not found",
        )

    try:
        await _role_service.assign_scope_to_role(
            db,
            role_id=role_id,
            scope_id=scope_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    logger.info(
        "ACTION: admin_role_scope_assign, admin_id=%s, role_id=%s, scope_id=%s",
        user.id,
        role_id,
        scope_id,
    )

    return MessageResponse(message=f"Scope '{scope.name}' assigned to role '{role.name}'")


@router.delete(
    "/{role_id}/scopes/{scope_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_scope_from_role(
    role_id: uuid.UUID,
    scope_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("roles:write"))],
) -> None:
    """Remove a scope assignment from a role.

    Returns `404` if the specified scope-to-role assignment does not exist.
    On success returns `204 No Content`.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/roles/550e8400-e29b-41d4-a716-446655440000/scopes/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```
    """
    role_scope = await _role_service.get_role_scope(db, role_id, scope_id)
    if not role_scope:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scope assignment not found",
        )

    await _role_service.remove_scope_from_role(db, role_scope)

    logger.info(
        "ACTION: admin_role_scope_unassign, admin_id=%s, role_id=%s, scope_id=%s",
        user.id,
        role_id,
        scope_id,
    )
