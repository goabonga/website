# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared dependencies for API v1 endpoints (Bearer token only)."""

import logging
import uuid
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, OAuth2AuthorizationCodeBearer
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_db,
    token_has_scope,
    validate_bearer_token,
    validate_pat_token,
)
from auth.db.models.tenant import Tenant, TenantMember
from auth.db.models.user import User
from auth.services.pat import PAT_PREFIX
from auth.services.tenant import tenant_service as _tenant_service
from auth.services.user import UserService

_user_service = UserService()

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="/oauth2/authorize",
    tokenUrl="/oauth2/token",
    auto_error=False,
)


async def get_current_user_bearer(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """Authenticate via Bearer token (access_token or PAT) and return the User.

    Raises:
        HTTPException 401: Missing or invalid token.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Build credentials for compatibility with validate_* functions
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    # Try PAT first
    if token.startswith(PAT_PREFIX):
        pat_auth = await validate_pat_token(request, db, credentials)
        if not pat_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired personal access token",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
        user = await _user_service.get_by_id(db, uuid.UUID(pat_auth.user_id))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
        request.state.auth_scopes = pat_auth.scopes
        request.state.auth_type = "pat"
        # PATs have no pairwise context; use the real user_id
        request.state.pairwise_sub = str(user.id)
        return user

    # Extract original JWT sub before pairwise resolution
    original_jwt_sub: str | None = None
    try:
        unverified = pyjwt.decode(token, options={"verify_signature": False})
        original_jwt_sub = unverified.get("sub")
    except pyjwt.DecodeError:
        pass

    # Try Bearer JWT
    bearer_auth = await validate_bearer_token(request, db, credentials)
    if not bearer_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    if not bearer_auth.subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has no associated user",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    user = await _user_service.get_by_id(db, uuid.UUID(bearer_auth.subject))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    request.state.auth_scopes = bearer_auth.scopes
    request.state.auth_type = "bearer"
    # Store the original JWT sub (pairwise or real) for profile responses.
    # When pairwise is enabled, this is the pairwise identifier from the JWT.
    # When disabled (or for old tokens), this equals bearer_auth.subject.
    request.state.pairwise_sub = original_jwt_sub or str(user.id)
    return user


def require_admin_scope(scope: str):
    """Dependency that checks the authenticated user has an admin-level scope."""

    async def dependency(
        request: Request,
        user: Annotated[User, Depends(get_current_user_bearer)],
    ) -> User:
        scopes = getattr(request.state, "auth_scopes", [])
        if not token_has_scope(scopes, scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {scope}",
            )
        return user

    return dependency


async def require_org_membership(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    required_scope: str,
) -> tuple[User, Tenant, TenantMember]:
    """Check user is a member of the org and holds the scope the operation requires.

    The scope has no default: a route that forgets it fails at once instead of
    letting every member through.

    Returns:
        Tuple of (user, tenant, membership).

    Raises:
        HTTPException 404: Org not found.
        HTTPException 403: Not a member or missing scope.
    """
    tenant = await _tenant_service.get_active_by_id(db, org_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")

    membership: TenantMember | None = await _tenant_service.get_member(db, org_id, user.id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organisation",
        )

    if not membership.has_scope(required_scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {required_scope}",
        )

    return user, tenant, membership


async def get_org_member_count(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Get total member count for an organisation."""
    return await _tenant_service.count_members(db, org_id)
