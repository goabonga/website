# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authorized applications API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_token_service
from auth.api.routes.api.deps import get_current_user_bearer
from auth.api.schemas.api.me import ApplicationResponse
from auth.db.models.user import User
from auth.services.token import TokenService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["me-applications"])


@router.get("/", response_model=list[ApplicationResponse])
async def list_authorized_applications(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
) -> list[ApplicationResponse]:
    """List OAuth2 applications the current user has authorized.

    Returns every OAuth2 client for which the authenticated user has at least
    one active access or refresh token (i.e. has granted consent). Use this
    list to display the "Connected applications" screen in a settings UI.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/applications/
    ```
    """
    clients = await token_service.get_user_authorized_clients(db, user.id)
    return [ApplicationResponse(**c) for c in clients]


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_application_access(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
) -> None:
    """Revoke all tokens granted to a specific OAuth2 application.

    Invalidates every active access token and refresh token the current user
    has issued to the given client. After revocation, the application must
    re-request authorization. Returns 404 if the client ID is unknown or the
    user has no active tokens for it.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X DELETE -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/applications/my-oauth2-client-id
    ```
    """
    revoked = await token_service.revoke_client_access(db, user.id, client_id)
    if revoked == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found or no active tokens",
        )
    await db.commit()
    logger.info(
        "ACTION: application_access_revoke_api_v1, user_id=%s, client_id=%s, revoked=%d",
        user.id,
        client_id,
        revoked,
    )
