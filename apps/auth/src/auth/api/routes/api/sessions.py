# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin sessions API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import require_admin_scope
from auth.api.schemas.api.common import MessageResponse, PaginatedResponse
from auth.api.schemas.api.sessions import SessionResponse
from auth.db.models.user import Session, User
from auth.services.session import SessionService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

_session_service = SessionService()
_user_service = UserService()


def _session_to_response(session: Session, primary_email: str | None = None) -> SessionResponse:
    """Build an ``SessionResponse`` from a ``Session`` model."""
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        user_email=primary_email,
        ip_address=session.ip_address,
        user_agent=session.user_agent,
        expires_at=session.expires_at,
        revoked_at=session.revoked_at,
        created_at=session.created_at,
    )


def _primary_email_from_user(user: User | None) -> str | None:
    """Extract the primary email from a user (or fall back to the first one)."""
    if not user or not user.emails:
        return None
    for e in user.emails:
        if e.is_primary:
            return e.email
    return user.emails[0].email


@router.get("/", response_model=PaginatedResponse[SessionResponse])
async def list_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("sessions:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: uuid.UUID | None = Query(None, description="Filter sessions for a specific user."),
    active_only: bool = Query(
        False,
        description="Return only sessions that are neither revoked nor expired.",
    ),
) -> PaginatedResponse[SessionResponse]:
    """List all active and revoked sessions across all users.

    Returns a paginated list of sessions ordered by creation date descending.
    Each item includes the associated user's primary email address when available.

    When ``user_id`` is provided the list is restricted to that user's sessions.
    When ``active_only=true`` only sessions that are neither revoked nor expired
    are returned.

    **Required scope:** `sessions:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/sessions/?page=1&page_size=20&active_only=true"
    ```
    """
    sessions, total = await _session_service.list_sessions(
        db,
        page=page,
        page_size=page_size,
        user_id=user_id,
        active_only=active_only,
        with_user=True,
    )

    items: list[SessionResponse] = [
        _session_to_response(s, _primary_email_from_user(s.user)) for s in sessions
    ]

    return PaginatedResponse[SessionResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("sessions:read"))],
) -> SessionResponse:
    """Get a single session by ID.

    Returns the full session record including owner, user agent, IP address,
    expiration and revocation timestamps. The associated user's primary email
    address is included when available. Returns 404 if no session exists with
    that ID.

    **Required scope:** `sessions:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/sessions/550e8400-e29b-41d4-a716-446655440000
    ```

    **Responses:**
    - `200` — session found
    - `403` — missing `sessions:read` scope
    - `404` — session not found
    """
    session = await _session_service.get_session_by_id_with_user(db, session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    primary_email = _primary_email_from_user(session.user)
    if primary_email is None:
        primary_email = await _user_service.get_primary_email(db, session.user_id)

    return _session_to_response(session, primary_email)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("sessions:revoke"))],
) -> Response:
    """Revoke a specific session by its ID.

    Sets `revoked_at` to the current timestamp on the session, immediately
    invalidating it. Returns 404 if the session does not exist or is already
    revoked.

    **Required scope:** `sessions:revoke`

    **Example:**
    ```
    curl -X DELETE -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/sessions/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    session = await _session_service.revoke_session_by_id_admin(db, session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    logger.info(
        "ACTION: session_revoke_admin_api_v1, admin_user_id=%s, session_id=%s, target_user_id=%s",
        user.id,
        session_id,
        session.user_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/", response_model=MessageResponse)
async def revoke_all_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("sessions:revoke"))],
    user_id: uuid.UUID | None = Query(
        None,
        description="If provided, only revoke sessions belonging to this user.",
    ),
) -> MessageResponse:
    """Revoke all currently active sessions across all users.

    Sets `revoked_at` on every session that is neither already revoked nor
    expired. Returns the total count of sessions that were revoked. This
    action cannot be undone.

    When ``user_id`` is provided, only sessions belonging to that user are
    revoked; otherwise every active session on the platform is revoked.

    **Required scope:** `sessions:revoke`

    **Example:**
    ```
    curl -X DELETE -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/sessions/?user_id=550e8400-e29b-41d4-a716-446655440000"
    ```
    """
    revoked_count = await _session_service.revoke_all_active_sessions(db, user_id=user_id)

    logger.info(
        "ACTION: sessions_revoke_all_api_v1, admin_user_id=%s, revoked_count=%d, filter_user_id=%s",
        user.id,
        revoked_count,
        user_id,
    )

    return MessageResponse(message=f"Revoked {revoked_count} session(s)")
