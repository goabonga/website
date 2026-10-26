# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /users admin endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import require_admin_scope
from auth.api.schemas.api.common import PaginatedResponse
from auth.api.schemas.api.users import (
    CreateUserRequest,
    UpdateUserRequest,
    UserResponse,
)
from auth.db.models.user import User
from auth.services.profile import ProfileData, ProfileService
from auth.services.session import SessionService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["admin-users"])

_user_service = UserService()
_session_service = SessionService()
_profile_service = ProfileService()

# Profile fields that can be updated via PATCH /users/{id}
_PROFILE_FIELDS: tuple[str, ...] = ("name", "given_name", "family_name", "nickname")


def _user_to_response(user: User) -> UserResponse:
    """Build a UserResponse from a User model."""
    primary_email = ""
    for email_obj in user.emails or []:
        if email_obj.is_primary:
            primary_email = email_obj.email
            break
    profile = getattr(user, "profile", None)
    return UserResponse(
        id=user.id,
        email=primary_email,
        is_active=user.is_active,
        registration_source=user.registration_source,
        name=profile.name if profile else None,
        given_name=profile.given_name if profile else None,
        family_name=profile.family_name if profile else None,
        nickname=profile.nickname if profile else None,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Fetch a user by ID (with emails/profile) via the service, or raise 404."""
    user = await _user_service.get_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.get("/", response_model=PaginatedResponse[UserResponse])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[UserResponse]:
    """List all users with pagination.

    Returns a paginated list of all user accounts across the entire platform.
    Results are ordered by creation date descending. Each item includes the
    primary email address and account status.

    **Required scope:** `users:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/users/?page=1&page_size=20"
    ```
    """
    users, total = await _user_service.list(db, page=page, page_size=page_size)
    return PaginatedResponse[UserResponse](
        items=[_user_to_response(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    body: CreateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:write"))],
) -> UserResponse:
    """Create a new user account.

    Provisions a user with the supplied email and password. The account is
    active by default; pass `is_active: false` to create it in a disabled
    state. Returns 409 if the email address is already registered.

    **Required scope:** `users:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"email": "alice@example.com", "password": "s3cr3t!", "is_active": true}' \\
      https://auth.example.com/api/v1/users/
    ```
    """
    if await _user_service.email_exists(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    new_user = await _user_service.create_user(
        db,
        email=body.email,
        password=body.password,
        registration_source="admin",
    )

    if not body.is_active:
        await _user_service.set_active(db, new_user, active=False)

    # Reload with emails + profile via the service
    reloaded = await _user_service.get_by_id(db, new_user.id)
    assert reloaded is not None  # Just created, must exist

    logger.info(
        "ACTION: admin_user_create, admin_id=%s, new_user_id=%s, email=%s",
        user.id,
        reloaded.id,
        body.email,
    )

    return _user_to_response(reloaded)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:read"))],
) -> UserResponse:
    """Get a single user by ID.

    Returns the full admin profile of one user, including their primary email
    address, account status, and registration source. Returns 404 if no user
    with the given ID exists.

    **Required scope:** `users:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/users/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    target = await _get_user_or_404(db, user_id)
    return _user_to_response(target)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:write"))],
) -> UserResponse:
    """Partially update a user account.

    Applies a sparse update — only fields present in the request body are
    modified. Omitted fields retain their current values. Returns 404 if the
    user does not exist.

    Supports updating the activation flag (``is_active``) and the OIDC
    profile fields ``name``, ``given_name``, ``family_name`` and
    ``nickname``. Profile changes are propagated to the user's
    :class:`UserProfile`; one is created on demand if the user had none.
    Fields omitted from the request body are left untouched.

    **Required scope:** `users:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"is_active": false, "given_name": "Alice"}' \\
      https://auth.example.com/api/v1/users/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    target = await _get_user_or_404(db, user_id)

    update_data = body.model_dump(exclude_unset=True)

    # Apply is_active on the User row itself via the service.
    if "is_active" in update_data and update_data["is_active"] is not None:
        await _user_service.set_active(db, target, active=update_data["is_active"])

    # Propagate profile fields through ProfileService when any were provided
    # with a non-null value (matches admin sparse-update semantics: explicit
    # null is treated as "leave untouched", not as "clear").
    profile_updates = {
        field: update_data[field]
        for field in _PROFILE_FIELDS
        if field in update_data and update_data[field] is not None
    }
    if profile_updates:
        await _profile_service.update_profile(
            db,
            str(target.id),
            ProfileData(**profile_updates),
        )

    # Reload so the response reflects the freshly-persisted profile.
    target = await _get_user_or_404(db, user_id)

    logger.info(
        "ACTION: admin_user_update, admin_id=%s, target_user_id=%s",
        user.id,
        user_id,
    )

    return _user_to_response(target)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:delete"))],
) -> None:
    """Permanently delete a user account.

    Removes the user record and all associated data (emails, sessions, etc.)
    from the database. This action is irreversible. Returns 204 on success and
    404 if the user does not exist.

    **Required scope:** `users:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/users/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    target = await _get_user_or_404(db, user_id)
    await _user_service.delete(db, target)

    logger.info(
        "ACTION: admin_user_delete, admin_id=%s, target_user_id=%s",
        user.id,
        user_id,
    )


@router.post("/{user_id}/disable", response_model=UserResponse)
async def disable_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:write"))],
) -> UserResponse:
    """Disable a user account.

    Sets `is_active` to `false`, preventing the user from authenticating.
    Existing sessions are not revoked automatically — call
    `DELETE /{user_id}/sessions` if immediate invalidation is required.
    Returns 400 if the account is already disabled.

    **Required scope:** `users:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/users/550e8400-e29b-41d4-a716-446655440000/disable
    ```
    """
    target = await _get_user_or_404(db, user_id)

    if not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already disabled",
        )

    await _user_service.set_active(db, target, active=False)

    logger.info(
        "ACTION: admin_user_disable, admin_id=%s, target_user_id=%s",
        user.id,
        user_id,
    )

    return _user_to_response(target)


@router.post("/{user_id}/enable", response_model=UserResponse)
async def enable_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:write"))],
) -> UserResponse:
    """Enable a previously disabled user account.

    Sets `is_active` to `true`, restoring the user's ability to authenticate.
    Returns 400 if the account is already active.

    **Required scope:** `users:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/users/550e8400-e29b-41d4-a716-446655440000/enable
    ```
    """
    target = await _get_user_or_404(db, user_id)

    if target.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already active",
        )

    await _user_service.set_active(db, target, active=True)

    logger.info(
        "ACTION: admin_user_enable, admin_id=%s, target_user_id=%s",
        user.id,
        user_id,
    )

    return _user_to_response(target)


@router.delete("/{user_id}/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("users:write"))],
) -> None:
    """Revoke all active sessions for a user.

    Immediately invalidates every session belonging to the specified user,
    forcing a re-login on all devices. Returns 204 on success regardless of
    how many sessions were terminated (including zero).

    **Required scope:** `users:write`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/users/550e8400-e29b-41d4-a716-446655440000/sessions
    ```
    """
    await _get_user_or_404(db, user_id)

    count = await _session_service.revoke_all_user_sessions(db, str(user_id))

    logger.info(
        "ACTION: admin_user_sessions_revoke, admin_id=%s, target_user_id=%s, count=%d",
        user.id,
        user_id,
        count,
    )
