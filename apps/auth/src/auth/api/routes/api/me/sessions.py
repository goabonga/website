# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Sessions API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_session_service
from auth.api.routes.api.deps import get_current_user_bearer
from auth.api.schemas.api.me import SessionResponse
from auth.db.models.user import User
from auth.services.session import SessionService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> list[SessionResponse]:
    """List all active sessions for the current user.

    Returns every session that is currently active for the authenticated user,
    ordered by creation time. Expired or previously revoked sessions are not
    included.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/sessions
    ```
    """
    sessions = await session_service.get_user_sessions(db, str(user.id))
    return [SessionResponse.model_validate(s) for s in sessions]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Revoke a specific session by ID.

    Immediately invalidates the target session. The caller can only revoke
    sessions that belong to their own account; attempting to revoke another
    user's session returns 404. Returns 204 on success with no response body.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X DELETE -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/sessions/550e8400-e29b-41d4-a716-446655440000
    ```

    **Responses:**
    - `204` — session revoked successfully
    - `404` — session not found or does not belong to the current user
    """
    revoked = await session_service.revoke_session_by_id(db, str(user.id), str(session_id))
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    logger.info("ACTION: session_revoke_api_v1, user_id=%s, session_id=%s", user.id, session_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
