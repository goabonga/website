# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin PAT management API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_pat_service
from auth.api.routes.api.deps import require_admin_scope
from auth.api.schemas.api.common import MessageResponse, PaginatedResponse
from auth.api.schemas.api.pats import PATDetailResponse, PATResponse
from auth.db.models.user import User
from auth.services.pat import PersonalAccessTokenService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pats", tags=["pats"])

_user_service = UserService()


def _primary_email(user: User | None) -> str | None:
    """Return the primary email for a user loaded with its ``emails``."""
    if user is None:
        return None
    for email in user.emails or []:
        if email.is_primary:
            return email.email
    return None


@router.get("/", response_model=PaginatedResponse[PATResponse])
async def list_pats(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("pats:read"))],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_revoked: bool = Query(False),
) -> PaginatedResponse[PATResponse]:
    """List all personal access tokens across all users.

    Returns a paginated list of PATs. Revoked tokens are excluded by default;
    set `include_revoked=true` to include them. Results are ordered by
    creation date descending.

    **Required scope:** `pats:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/pats/?page=1&page_size=20&include_revoked=false"
    ```
    """
    offset = (page - 1) * page_size
    tokens, total = await pat_service.list_all_tokens(
        db, include_revoked=include_revoked, offset=offset, limit=page_size
    )

    return PaginatedResponse[PATResponse](
        items=[PATResponse.model_validate(t) for t in tokens],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{pat_id}", response_model=PATDetailResponse)
async def get_pat(
    pat_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("pats:read"))],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> PATDetailResponse:
    """Get a single personal access token by ID (admin view).

    Returns the full PAT record, including ownership context (owning user's
    primary email, tenant, target client) and usage counters. Returns `404`
    if the token does not exist.

    **Required scope:** `pats:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/pats/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    pat = await pat_service.get_token_by_id(db, pat_id)

    if not pat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    owner = await _user_service.get_by_id(db, pat.user_id)
    user_email = _primary_email(owner)

    return PATDetailResponse(
        id=pat.id,
        user_id=pat.user_id,
        user_email=user_email,
        tenant_id=pat.tenant_id,
        target_client_id=pat.target_client_id,
        name=pat.name,
        token_suffix=pat.token_suffix,
        scopes=list(pat.scopes),
        description=pat.description,
        expires_at=pat.expires_at,
        revoked_at=pat.revoked_at,
        last_used_at=pat.last_used_at,
        last_used_ip=pat.last_used_ip,
        use_count=pat.use_count,
        created_at=pat.created_at,
    )


@router.delete("/{pat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_pat(
    pat_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("pats:revoke"))],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> Response:
    """Revoke a single personal access token by ID.

    Marks the token as revoked with the reason `admin_revocation`. The token
    can no longer be used for authentication after this call. Returns `404`
    if the token does not exist or has already been revoked.

    **Required scope:** `pats:revoke`

    **Example:**
    ```
    curl -X DELETE -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/pats/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    success = await pat_service.revoke_token(
        db, pat_id, revoked_by=user.id, reason="admin_revocation"
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    await db.commit()

    logger.info("ACTION: pat_admin_revoke_api_v1, admin_id=%s, pat_id=%s", user.id, pat_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/", response_model=MessageResponse)
async def revoke_all_pats(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("pats:revoke"))],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    reason: Annotated[str | None, Query(max_length=255)] = None,
) -> MessageResponse:
    """Revoke active personal access tokens, optionally filtered by user.

    When `user_id` is provided, bulk-revokes every active token owned by that
    user via `PersonalAccessTokenService.bulk_revoke`. When `user_id` is
    omitted, bulk-revokes every active token across all users. The admin ID
    is recorded on each token; the reason defaults to `admin_bulk_revocation`
    (or `admin_user_bulk_revocation` when scoped to a single user) but can be
    overridden via the `reason` query parameter. Returns the count of tokens
    that were revoked.

    **Required scope:** `pats:revoke`

    **Example:**
    ```
    curl -X DELETE -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/pats/?user_id=550e8400-e29b-41d4-a716-446655440000&reason=offboarding"
    ```
    """
    if user_id is not None:
        revocation_reason = reason or "admin_user_bulk_revocation"
        count = await pat_service.bulk_revoke(
            db,
            user_id,
            revoked_by=user.id,
            reason=revocation_reason,
        )

        logger.info(
            "ACTION: pats_revoke_user_api_v1, admin_user_id=%s, target_user_id=%s, revoked_count=%d",
            user.id,
            user_id,
            count,
        )

        return MessageResponse(message=f"Revoked {count} token(s)")

    revocation_reason = reason or "admin_bulk_revocation"
    count = await pat_service.bulk_revoke_all(
        db,
        revoked_by=user.id,
        reason=revocation_reason,
    )

    logger.info(
        "ACTION: pats_revoke_all_api_v1, admin_user_id=%s, revoked_count=%d",
        user.id,
        count,
    )

    return MessageResponse(message=f"Revoked {count} token(s)")
