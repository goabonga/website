# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 token introspection endpoint (RFC 7662)."""

import base64
import logging
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Form, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_oauth2_client_service, get_pat_service, get_token_service
from auth.api.schemas.oauth2 import IntrospectionResponse, OAuth2Error, TokenErrorResponse
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.pairwise import PairwiseSubjectService
from auth.services.pat import PAT_PREFIX, PersonalAccessTokenService
from auth.services.tenant import TenantService
from auth.services.token import TokenService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_basic_auth(authorization: str | None) -> tuple[str | None, str | None]:
    """Parse Basic authentication header."""
    if not authorization or not authorization.startswith("Basic "):
        return None, None

    try:
        encoded = authorization[6:]
        decoded = base64.b64decode(encoded).decode("utf-8")
        client_id, client_secret = decoded.split(":", 1)
        return client_id, client_secret
    except (ValueError, UnicodeDecodeError):
        return None, None


@router.post(
    "/introspect",
    response_model=IntrospectionResponse,
    responses={
        401: {"model": TokenErrorResponse, "description": "Invalid client"},
    },
)
async def introspect_token(
    token: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth2_service: Annotated[OAuth2ClientService, Depends(get_oauth2_client_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    authorization: Annotated[str | None, Header()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
    token_type_hint: Annotated[str | None, Form()] = None,
) -> IntrospectionResponse:
    """Validate a token and return its active state and metadata.

    Resource servers call this endpoint to verify a token without needing
    access to JWT signing keys or a local token store. If the token is
    invalid, expired, or revoked, the response is always
    `{"active": false}` — no additional fields are returned, so callers
    cannot distinguish between a never-issued and a revoked token.
    Providing `token_type_hint` (`access_token` or `refresh_token`) is
    optional but allows the server to skip an unnecessary lookup pass when
    the caller already knows the token type. Personal Access Tokens (PAT)
    are also supported and are identified automatically by their prefix.

    **Specification:** RFC 7662 §2.1 (request) / §2.2 (response).
    Client authentication follows RFC 6749 §2.3. Public clients are not
    permitted to call this endpoint.

    **Authentication:** client credentials (HTTP Basic per
    RFC 6749 §2.3.1, or `client_id` + `client_secret` in the form body).
    Public clients are not permitted.

    **Example:**
    ```
    curl -X POST \\
      -u "my-resource-server:s3cr3t" \\
      -d "token=mF_9.B5f-4.1JqM&token_type_hint=access_token" \\
      https://auth.example.com/oauth2/introspect
    ```
    """
    logger.info(
        "Token introspection request: client_id=%s, token_type_hint=%s", client_id, token_type_hint
    )

    # Parse client credentials
    basic_client_id, basic_client_secret = _parse_basic_auth(authorization)
    effective_client_id = basic_client_id or client_id
    effective_client_secret = basic_client_secret or client_secret

    if not effective_client_id:
        logger.warning("Token introspection failed: client authentication required")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=TokenErrorResponse(
                error=OAuth2Error.INVALID_CLIENT,
                error_description="Client authentication required",
            ).model_dump(),
            headers={"WWW-Authenticate": "Basic"},
        )

    # Get and verify client
    client = await oauth2_service.get_client_by_client_id(db, effective_client_id)
    if not client or not client.is_active:
        logger.warning("Token introspection failed: invalid client %s", effective_client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=TokenErrorResponse(
                error=OAuth2Error.INVALID_CLIENT,
                error_description="Invalid client",
            ).model_dump(),
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify client secret for confidential clients
    if client.is_confidential:
        if not effective_client_secret:
            logger.warning(
                "Token introspection failed: client secret required for %s", effective_client_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=TokenErrorResponse(
                    error=OAuth2Error.INVALID_CLIENT,
                    error_description="Client authentication required",
                ).model_dump(),
                headers={"WWW-Authenticate": "Basic"},
            )

        if not oauth2_service.verify_client_secret(client, effective_client_secret):
            logger.warning(
                "Token introspection failed: invalid client credentials for %s", effective_client_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=TokenErrorResponse(
                    error=OAuth2Error.INVALID_CLIENT,
                    error_description="Invalid client credentials",
                ).model_dump(),
                headers={"WWW-Authenticate": "Basic"},
            )

    # Verify the client has the 'introspect' scope
    if "introspect" not in client.allowed_scopes:
        logger.warning(
            "Token introspection failed: client %s does not have 'introspect' scope",
            effective_client_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=TokenErrorResponse(
                error=OAuth2Error.INSUFFICIENT_SCOPE,
                error_description="Client is not authorized to introspect tokens",
            ).model_dump(),
        )

    # Fast path: if token has the PAT prefix, only try PAT introspection
    if token.startswith(PAT_PREFIX):
        result = await _introspect_pat(db, pat_service, token)
        logger.info(
            "ACTION: oauth2_token_introspect, client_id=%s, active=%s, type=pat",
            effective_client_id,
            result.active,
        )
        return result

    # Try to introspect based on token_type_hint
    if token_type_hint == "refresh_token":
        refresh_result = await _introspect_refresh_token(db, token_service, token)
        if refresh_result:
            logger.info(
                "ACTION: oauth2_token_introspect, client_id=%s, active=True, type=refresh_token",
                effective_client_id,
            )
            return refresh_result
        # Fall through to try as access token
        result = await _introspect_access_token(db, token_service, token)
        logger.info(
            "ACTION: oauth2_token_introspect, client_id=%s, active=%s, type=access_token",
            effective_client_id,
            result.active,
        )
        return result
    else:
        # Try access token first (default)
        result = await _introspect_access_token(db, token_service, token)
        if result.active:
            logger.info(
                "ACTION: oauth2_token_introspect, client_id=%s, active=True, type=access_token",
                effective_client_id,
            )
            return result
        # Try as refresh token
        refresh_result = await _introspect_refresh_token(db, token_service, token)
        if refresh_result:
            logger.info(
                "ACTION: oauth2_token_introspect, client_id=%s, active=True, type=refresh_token",
                effective_client_id,
            )
            return refresh_result
        logger.info(
            "ACTION: oauth2_token_introspect, client_id=%s, active=False", effective_client_id
        )
        return IntrospectionResponse(active=False)


async def _introspect_access_token(
    db: AsyncSession,
    token_service: TokenService,
    token: str,
) -> IntrospectionResponse:
    """Introspect an access token (JWT).

    Args:
        db: Database session.
        token_service: Token service.
        token: JWT token string.

    Returns:
        IntrospectionResponse with token details or inactive status.
    """
    try:
        # Decode without verification to get claims
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.DecodeError:
        return IntrospectionResponse(active=False)

    jti = unverified.get("jti")
    if not jti:
        return IntrospectionResponse(active=False)

    # Check if token exists and is valid in database
    access_token = await token_service.get_access_token_by_jti(db, jti)
    if not access_token:
        return IntrospectionResponse(active=False)

    # Check if revoked
    if access_token.revoked_at is not None:
        return IntrospectionResponse(active=False)

    # Check if expired
    now = datetime.now(UTC)
    if access_token.expires_at < now:
        return IntrospectionResponse(active=False)

    # Token is active
    return IntrospectionResponse(
        active=True,
        scope=unverified.get("scope"),
        client_id=unverified.get("client_id"),
        username=None,  # Could be populated from user lookup
        token_type="Bearer",
        exp=unverified.get("exp"),
        iat=unverified.get("iat"),
        nbf=unverified.get("nbf"),
        sub=unverified.get("sub"),
        aud=unverified.get("aud"),
        iss=unverified.get("iss"),
        jti=jti,
    )


async def _introspect_refresh_token(
    db: AsyncSession,
    token_service: TokenService,
    token: str,
) -> IntrospectionResponse | None:
    """Introspect a refresh token.

    Args:
        db: Database session.
        token_service: Token service.
        token: Refresh token string.

    Returns:
        IntrospectionResponse with token details or None if not found.
    """
    refresh_token = await token_service.get_refresh_token(db, token)
    if not refresh_token:
        return None

    # Always resolve pairwise sub
    sub_value = str(refresh_token.user_id) if refresh_token.user_id else None
    if sub_value and refresh_token.user_id:
        oauth2_client_service = OAuth2ClientService()
        client = await oauth2_client_service.get_by_id(db, refresh_token.client_id)
        if client:
            pairwise_service = PairwiseSubjectService()
            sub_value = await pairwise_service.get_sub_for_client(db, refresh_token.user_id, client)

    return IntrospectionResponse(
        active=True,
        scope=" ".join(refresh_token.scopes) if refresh_token.scopes else None,
        client_id=str(refresh_token.client_id),
        username=None,
        token_type="refresh_token",
        exp=int(refresh_token.expires_at.timestamp()),
        iat=int(refresh_token.created_at.timestamp())
        if hasattr(refresh_token, "created_at")
        else None,
        nbf=None,
        sub=sub_value,
        aud=None,
        iss=None,
        jti=None,
    )


async def _introspect_pat(
    db: AsyncSession,
    pat_service: PersonalAccessTokenService,
    token: str,
) -> IntrospectionResponse:
    """Introspect a Personal Access Token.

    Args:
        db: Database session.
        pat_service: PAT service.
        token: Plain PAT string (gab_pat_...).

    Returns:
        IntrospectionResponse with token details or inactive status.
    """
    pat = await pat_service.validate_token(db, token)
    if not pat:
        return IntrospectionResponse(active=False)

    # Resolve username via service (eager-loads user + emails + profile).
    # Prefer the primary email, fall back to any email associated with the user.
    username: str | None = None
    if pat.user_id:
        user_service = UserService()
        user = await user_service.get_by_id(db, pat.user_id)
        if user and user.emails:
            primary = next((e for e in user.emails if e.is_primary), None)
            username = primary.email if primary else user.emails[0].email

    # Always resolve pairwise sub for PATs with tenant context
    sub_value = str(pat.user_id)
    if pat.tenant_id:
        tenant_service = TenantService()
        tenant = await tenant_service.get_by_id(db, pat.tenant_id)
        if tenant:
            pairwise_service = PairwiseSubjectService()
            sub_value = await pairwise_service.get_or_create_sub(db, pat.user_id, tenant.id)

    return IntrospectionResponse(
        active=True,
        scope=" ".join(pat.scopes) if pat.scopes else None,
        client_id=str(pat.target_client_id) if pat.target_client_id else None,
        username=username,
        token_type="pat",
        exp=int(pat.expires_at.timestamp()) if pat.expires_at else None,
        iat=int(pat.created_at.timestamp()) if pat.created_at else None,
        nbf=None,
        sub=sub_value,
        aud=None,
        iss=None,
        jti=str(pat.id),
    )
