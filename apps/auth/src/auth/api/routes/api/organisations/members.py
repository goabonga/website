# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /organisations/{org_id}/members endpoints."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.common import PaginatedResponse
from auth.api.schemas.api.organisations import (
    AddMemberRequest,
    MemberResponse,
    UpdateMemberRequest,
)
from auth.db.models.tenant import TenantMember
from auth.db.models.user import User
from auth.services.tenant import tenant_service as _tenant_service
from auth.services.tenant_role import tenant_role_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["organisation-members"])


def _build_member_response(member: TenantMember) -> MemberResponse:
    """Build a MemberResponse from a TenantMember model."""
    return MemberResponse(
        user_id=member.user_id,
        role_id=member.role_id,
        role_name=member.role_name,
        role_display_name=member.role_display_name,
        joined_at=member.joined_at,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get("/", response_model=PaginatedResponse[MemberResponse])
async def list_members(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[MemberResponse]:
    """List all members of an organisation with pagination.

    Returns a paginated list of members belonging to the specified organisation,
    ordered by join date descending. Each entry includes the member's user ID,
    assigned role, and timestamps.

    **Required scope:** org membership + `members:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/members/?page=1&page_size=20"
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="members:read"
    )

    total = await _tenant_service.count_members(db, tenant.id)
    members = await _tenant_service.list_members(db, tenant.id, page=page, page_size=page_size)

    items = [_build_member_response(m) for m in members]

    return PaginatedResponse[MemberResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    org_id: uuid.UUID,
    body: AddMemberRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> MemberResponse:
    """Add a user to an organisation.

    Creates a membership record for the specified user within the organisation.
    If no `role_id` is provided, the user is assigned the organisation's default
    `member` role. Returns `409` if the user is already a member.

    **Required scope:** org membership + `members:invite`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"user_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8", "role_id": null}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/members/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="members:invite"
    )

    # Check if user is already a member
    existing = await _tenant_service.get_member(db, tenant.id, body.user_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organisation",
        )

    # Resolve role
    role = None
    if body.role_id:
        role = await tenant_role_service.get_role_by_id(db, body.role_id)
        if not role or role.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role not found in this organisation",
            )
    else:
        # Default to "member" role
        role = await tenant_role_service.get_role_by_name(db, tenant.id, "member")

    member = TenantMember(
        tenant_id=tenant.id,
        user_id=body.user_id,
        role_id=role.id if role else None,
        invited_by=user.id,
        invited_at=datetime.now(UTC),
        joined_at=datetime.now(UTC),
    )
    await _tenant_service.add_member(db, member)
    await db.commit()

    # Reload with role eager-loaded
    reloaded = await _tenant_service.get_member_by_id(db, member.id, eager_role=True)
    if reloaded is not None:
        member = reloaded

    logger.info(
        "ACTION: member_add, org_id=%s, user_id=%s, target_user_id=%s, role=%s",
        tenant.id,
        user.id,
        body.user_id,
        member.role_name,
    )

    return _build_member_response(member)


@router.patch("/{user_id}", response_model=MemberResponse)
async def update_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMemberRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> MemberResponse:
    """Update the role assigned to an organisation member.

    Replaces the member's current role with the specified `role_id`. The role
    must belong to the same organisation; cross-organisation role assignment is
    rejected with `400`. Returns `404` if the user is not a member.

    **Required scope:** org membership + `members:update`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"role_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}' \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/members/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="members:update"
    )

    # Find the target member
    member = await _tenant_service.get_member(db, tenant.id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Resolve new role
    role = await tenant_role_service.get_role_by_id(db, body.role_id)
    if not role or role.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role not found in this organisation",
        )

    await tenant_role_service.assign_role(db, member, role)
    await db.commit()

    # Reload with updated role eager-loaded
    reloaded = await _tenant_service.get_member_by_id(db, member.id, eager_role=True)
    if reloaded is not None:
        member = reloaded

    logger.info(
        "ACTION: member_update_role, org_id=%s, user_id=%s, target_user_id=%s, new_role=%s",
        tenant.id,
        user.id,
        user_id,
        member.role_name,
    )

    return _build_member_response(member)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> None:
    """Remove a user from an organisation.

    Permanently deletes the membership record for the specified user. This action
    does not delete the user account itself. Returns `404` if the user is not
    currently a member of the organisation.

    **Required scope:** org membership + `members:remove`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/organisations/550e8400-e29b-41d4-a716-446655440000/members/6ba7b810-9dad-11d1-80b4-00c04fd430c8
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="members:remove"
    )

    # Find the target member
    member = await _tenant_service.get_member(db, tenant.id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    await _tenant_service.remove_member(db, member)
    await db.commit()

    logger.info(
        "ACTION: member_remove, org_id=%s, user_id=%s, target_user_id=%s",
        tenant.id,
        user.id,
        user_id,
    )
