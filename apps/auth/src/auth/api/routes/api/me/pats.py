# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Personal Access Token management API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_pat_service
from auth.api.routes.api.deps import get_current_user_bearer
from auth.api.schemas.api.common import PaginatedResponse
from auth.api.schemas.api.me import (
    PATCreateRequest,
    PATCreateResponse,
    PATResponse,
    PATUpdateRequest,
)
from auth.db.models.pat import PATExpirationPreset
from auth.db.models.user import User
from auth.services.pat import PersonalAccessTokenService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pats", tags=["me:pats"])


@router.get("/", response_model=PaginatedResponse[PATResponse])
async def list_tokens(
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[PATResponse]:
    """List all active personal access tokens for the authenticated user.

    Returns a paginated list of PATs belonging to the caller. Revoked tokens
    are excluded from the results.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/me/pats/?page=1&page_size=20"
    ```
    """
    offset = (page - 1) * page_size
    tokens, total = await pat_service.list_user_tokens(
        db, user.id, include_revoked=False, offset=offset, limit=page_size
    )

    return PaginatedResponse[PATResponse](
        items=[PATResponse.model_validate(t) for t in tokens],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=PATCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    body: PATCreateRequest,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> PATCreateResponse:
    """Create a new personal access token for the authenticated user.

    The raw token value is returned only once in the response field `token`.
    It cannot be retrieved again after this call — store it securely immediately.
    Scopes and expiration are configured at creation time.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "ci-deploy", "scopes": ["me:read"], "expiration_preset": "90d"}' \\
      https://auth.example.com/api/v1/me/pats/
    ```
    """
    pat, raw_token = await pat_service.create_token(
        db,
        user_id=user.id,
        name=body.name,
        scopes=body.scopes,
        description=body.description,
        expiration_preset=PATExpirationPreset(body.expiration_preset),
        custom_expiration_days=body.custom_expiration_days,
    )
    await db.commit()

    logger.info("ACTION: pat_create_api_v1, user_id=%s, pat_id=%s", user.id, pat.id)

    return PATCreateResponse(
        id=pat.id,
        name=pat.name,
        token=raw_token,
        scopes=pat.scopes,
        expires_at=pat.expires_at,
        created_at=pat.created_at,
    )


@router.get("/{token_id}", response_model=PATResponse)
async def get_token(
    token_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> PATResponse:
    """Retrieve metadata for a specific personal access token.

    Returns token details such as name, scopes, and expiration date.
    The raw secret value is never included in this response.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/pats/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    pat = await pat_service.get_token_by_id(db, token_id, user.id)

    if not pat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    return PATResponse.model_validate(pat)


@router.patch("/{token_id}", response_model=PATResponse)
async def update_token_scopes(
    token_id: uuid.UUID,
    body: PATUpdateRequest,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> PATResponse:
    """Update the scopes assigned to a personal access token.

    Replaces the token's scope list with the values provided in the request body.
    The token must be active (not revoked) and must belong to the authenticated user.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"scopes": ["me:read", "me:sessions:read"]}' \\
      https://auth.example.com/api/v1/me/pats/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    pat = await pat_service.update_token_scopes(db, token_id, user.id, body.scopes)

    if not pat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found or already revoked",
        )

    await db.commit()

    logger.info("ACTION: pat_update_scopes_api_v1, user_id=%s, pat_id=%s", user.id, token_id)

    return PATResponse.model_validate(pat)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> Response:
    """Revoke a personal access token, permanently invalidating it.

    Once revoked, the token cannot be used for authentication and will no longer
    appear in list results. This action is irreversible.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/pats/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    success = await pat_service.revoke_token(db, token_id, user_id=user.id, revoked_by=user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    await db.commit()

    logger.info("ACTION: pat_revoke_api_v1, user_id=%s, pat_id=%s", user.id, token_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{token_id}/regenerate", response_model=PATCreateResponse)
async def regenerate_token(
    token_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> PATCreateResponse:
    """Regenerate a personal access token, rotating its secret value.

    The existing token is immediately revoked and a new token is issued with the
    same name, scopes, and expiration settings. The new raw secret is returned
    only once in the `token` field — store it securely immediately.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/pats/550e8400-e29b-41d4-a716-446655440000/regenerate
    ```
    """
    result = await pat_service.regenerate_token(db, token_id, user.id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    new_pat, raw_token = result
    await db.commit()

    logger.info(
        "ACTION: pat_regenerate_api_v1, user_id=%s, old_pat_id=%s, new_pat_id=%s",
        user.id,
        token_id,
        new_pat.id,
    )

    return PATCreateResponse(
        id=new_pat.id,
        name=new_pat.name,
        token=raw_token,
        scopes=new_pat.scopes,
        expires_at=new_pat.expires_at,
        created_at=new_pat.created_at,
    )
