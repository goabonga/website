# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /scopes admin endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import require_admin_scope
from auth.api.schemas.api.common import PaginatedResponse
from auth.api.schemas.api.scopes import CreateScopeRequest, ScopeResponse, UpdateScopeRequest
from auth.db.models.rbac import Scope
from auth.db.models.user import User
from auth.services.scope import ScopeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scopes", tags=["scopes"])

_scope_service = ScopeService()


def _build_scope_response(scope: Scope) -> ScopeResponse:
    """Build a ScopeResponse from a Scope model."""
    return ScopeResponse(
        id=scope.id,
        name=scope.name,
        description=scope.description,
        resource=scope.resource,
        action=scope.action,
        category=scope.category,
        is_system=scope.is_system,
        is_active=scope.is_active,
        created_at=scope.created_at,
        updated_at=scope.updated_at,
    )


@router.get("/", response_model=PaginatedResponse[ScopeResponse])
async def list_scopes(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("scopes:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ScopeResponse]:
    """List all scopes with pagination.

    Returns a paginated list of all scopes registered in the system, ordered
    by creation date descending. Includes both system-managed and custom scopes.

    **Required scope:** `scopes:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/scopes/?page=1&page_size=20"
    ```
    """
    scopes, total = await _scope_service.list(db, page=page, page_size=page_size)

    items = [_build_scope_response(s) for s in scopes]

    return PaginatedResponse[ScopeResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=ScopeResponse, status_code=status.HTTP_201_CREATED)
async def create_scope(
    body: CreateScopeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("scopes:write"))],
) -> ScopeResponse:
    """Create a new custom scope.

    Creates a scope with the given name, resource, action, and category.
    The name must be unique across all scopes. System scopes (`is_system=true`)
    cannot be created via this endpoint; they are seeded automatically.

    **Required scope:** `scopes:write`

    **Responses:**
    - `201` — scope created
    - `409` — a scope with that name already exists

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "reports:read", "description": "Read reports", "resource": "reports", "action": "read", "category": "reporting"}' \\
      https://auth.example.com/api/v1/scopes/
    ```
    """
    # Check name uniqueness
    if await _scope_service.name_exists(db, body.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scope with name '{body.name}' already exists",
        )

    scope = Scope(
        name=body.name,
        description=body.description,
        resource=body.resource,
        action=body.action,
        category=body.category,
        is_system=False,
    )
    await _scope_service.stage(db, scope)
    await db.commit()
    await db.refresh(scope)

    return _build_scope_response(scope)


@router.get("/{scope_id}", response_model=ScopeResponse)
async def get_scope(
    scope_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("scopes:read"))],
) -> ScopeResponse:
    """Get a single scope by its UUID.

    Returns the full scope record including its resource, action, category,
    and whether it is a system-managed scope.

    **Required scope:** `scopes:read`

    **Responses:**
    - `200` — scope found
    - `404` — scope not found

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/scopes/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    scope = await _scope_service.get_by_id(db, scope_id)
    if not scope:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scope not found",
        )
    return _build_scope_response(scope)


@router.patch("/{scope_id}", response_model=ScopeResponse)
async def update_scope(
    scope_id: uuid.UUID,
    body: UpdateScopeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("scopes:write"))],
) -> ScopeResponse:
    """Partially update a scope.

    All fields are optional; only provided fields are updated. If `name` is
    changed, uniqueness is enforced and a `409` is returned on conflict.
    System scopes can be updated via this endpoint (e.g. to adjust description
    or category), but cannot be deleted.

    **Required scope:** `scopes:write`

    **Responses:**
    - `200` — scope updated
    - `404` — scope not found
    - `409` — name already taken by another scope

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"description": "Updated description", "category": "reporting"}' \\
      https://auth.example.com/api/v1/scopes/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    scope = await _scope_service.get_by_id(db, scope_id)
    if not scope:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scope not found",
        )

    if body.name is not None:
        if body.name != scope.name and await _scope_service.name_exists(db, body.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Scope with name '{body.name}' already exists",
            )
        scope.name = body.name

    if body.description is not None:
        scope.description = body.description
    if body.resource is not None:
        scope.resource = body.resource
    if body.action is not None:
        scope.action = body.action
    if body.category is not None:
        scope.category = body.category

    await db.commit()
    await db.refresh(scope)

    return _build_scope_response(scope)


@router.delete("/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scope(
    scope_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("scopes:delete"))],
) -> None:
    """Delete a scope by its UUID.

    Permanently removes the scope record. Scopes marked `is_system=true` are
    protected and will return `400` if deletion is attempted. Ensure no roles
    or clients reference this scope before deleting to avoid orphaned grants.

    **Required scope:** `scopes:delete`

    **Responses:**
    - `204` — scope deleted
    - `400` — scope is a system scope and cannot be deleted
    - `404` — scope not found

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/scopes/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    scope = await _scope_service.get_by_id(db, scope_id)
    if not scope:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scope not found",
        )

    if scope.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System scopes cannot be deleted",
        )

    await _scope_service.delete(db, scope)
    await db.commit()
