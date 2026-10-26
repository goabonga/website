# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Password change API endpoint."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_auth_service, get_db, get_password_service
from auth.api.routes.api.deps import get_current_user_bearer
from auth.api.schemas.api.common import MessageResponse
from auth.api.schemas.api.me import PasswordChangeRequest
from auth.db.models.user import User
from auth.services.auth import AuthService
from auth.services.password import PasswordService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.put("/password", response_model=MessageResponse)
async def change_password(
    body: PasswordChangeRequest,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    password_service: Annotated[PasswordService, Depends(get_password_service)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    """Change the authenticated user's password.

    Verifies the supplied `current_password` against the user's primary email
    credential before applying the change. All other active sessions are NOT
    automatically revoked — callers that need that behaviour should follow up
    with a session revocation call.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"current_password": "OldP@ssw0rd!", "new_password": "NewP@ssw0rd!"}' \\
      https://auth.example.com/api/v1/me/password
    ```
    """
    # Get the user's primary email for credential verification
    primary_email = next(
        (e.email for e in user.emails if e.is_primary),
        None,
    )
    if not primary_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No primary email found for user",
        )

    # Verify current credentials
    verified = await auth_service.verify_credentials(db, primary_email, body.current_password)
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Change password
    success, error = await password_service.change_password(
        db, str(user.id), body.current_password, body.new_password
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Password change failed",
        )

    logger.info("ACTION: password_change_api_v1, user_id=%s", user.id)

    return MessageResponse(message="Password changed successfully")
