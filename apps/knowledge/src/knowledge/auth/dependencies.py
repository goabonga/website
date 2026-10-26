# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI authentication dependencies."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2AuthorizationCodeBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.jwt import JWTValidationError, get_jwt_validator
from knowledge.auth.models import User
from knowledge.auth.token_exchange import TokenExchangeError, get_token_exchange_client
from knowledge.config import get_settings
from knowledge.database import get_db

logger = logging.getLogger(__name__)
settings = get_settings()

# Knowledge API scopes for token exchange
# These are the scopes that the API needs - RBAC will filter to what user has
KNOWLEDGE_API_SCOPES = [
    "collections:read",
    "collections:write",
    "collections:search",
    "documents:read",
    "documents:write",
]

# HTTP Bearer scheme for API auth (fallback)
bearer_scheme = HTTPBearer(auto_error=False)


def _get_oauth2_scheme() -> OAuth2AuthorizationCodeBearer | None:
    """Create OAuth2 Authorization Code scheme for Swagger UI.

    Uses PKCE (Proof Key for Code Exchange) for secure browser-based auth.
    Only requests openid, profile, email scopes (no offline_access for Swagger).
    """
    if not settings.oauth2_issuer or not settings.oauth2_swagger_client_id:
        return None

    return OAuth2AuthorizationCodeBearer(
        authorizationUrl=f"{settings.oauth2_issuer}/oauth2/authorize",
        tokenUrl=f"{settings.oauth2_issuer}/oauth2/token",
        scopes={
            "openid": "OpenID Connect authentication",
            "profile": "Access to user profile information",
            "email": "Access to user email address",
        },
        auto_error=False,
    )


# OAuth2 scheme for Swagger UI (initialized lazily)
_oauth2_scheme: OAuth2AuthorizationCodeBearer | None = None


def get_oauth2_scheme() -> OAuth2AuthorizationCodeBearer | None:
    """Get or create the OAuth2 scheme singleton."""
    global _oauth2_scheme
    if _oauth2_scheme is None:
        _oauth2_scheme = _get_oauth2_scheme()
    return _oauth2_scheme


class AuthContext:
    """Authentication context for API requests."""

    def __init__(self, user: User, tenant_id: UUID | None = None) -> None:
        self.user = user
        self._tenant_id = tenant_id

    @property
    def user_id(self) -> UUID:
        """Get user ID."""
        return self.user.id

    @property
    def tenant_id(self) -> UUID:
        """Get tenant ID.

        For API requests, tenant_id defaults to user_id (personal tenant).
        This can be overridden by X-Tenant-ID header for multi-tenant support.
        """
        if self._tenant_id:
            return self._tenant_id
        # Default: use user_id as tenant_id (personal tenant)
        return self.user.id

    @property
    def scopes(self) -> list[str]:
        """Get user scopes."""
        return self.user.scopes

    def has_scope(self, scope: str) -> bool:
        """Check if the user has a specific scope."""
        return self.user.has_scope(scope)

    def require_scope(self, scope: str) -> None:
        """Require a specific scope, raising 403 if not present."""
        if not self.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {scope}",
            )


async def _get_token_from_oauth2_or_bearer(
    request: Request,
    oauth2_token: str | None = None,
    bearer_credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Extract token from OAuth2 scheme or Bearer header."""
    # Prefer OAuth2 token (from Swagger UI)
    if oauth2_token:
        return oauth2_token
    # Fall back to Bearer token
    if bearer_credentials:
        return bearer_credentials.credentials
    return None


async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    oauth2_token: str | None = Depends(get_oauth2_scheme() or (lambda: None)),
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    """Extract and validate authentication from request.

    Supports:
    - OAuth2 Authorization Code flow (Swagger UI)
    - Authorization: Bearer <jwt_token> (API clients)
    - X-Tenant-ID header for tenant context

    Uses token exchange (RFC 8693) to get API scopes based on user roles.
    When no X-Tenant-ID is provided, resolves user's default organization.
    """
    from knowledge.models import Organization, OrganizationMember

    token = await _get_token_from_oauth2_or_bearer(request, oauth2_token, bearer_credentials)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not settings.oauth2_issuer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth2 issuer not configured",
        )

    try:
        # Step 1: Validate the JWT signature and basic claims (identity)
        jwt_validator = get_jwt_validator()
        claims = await jwt_validator.validate_token_with_introspection(token)

        # Step 2: Use token exchange to get API scopes based on user roles
        api_scopes: list[str] = []
        if settings.oauth2_client_id and settings.oauth2_client_secret:
            try:
                token_exchange_client = get_token_exchange_client()
                # Exchange token requesting all Knowledge API scopes
                # RBAC will filter to only those the user has permission for
                logger.info(
                    f"Performing token exchange with client_id: {settings.oauth2_client_id}"
                )
                exchange_result = await token_exchange_client.exchange_token(
                    token, requested_scopes=KNOWLEDGE_API_SCOPES
                )
                # Extract scopes from the exchanged token
                scope_str = exchange_result.get("scope", "")
                api_scopes = scope_str.split() if scope_str else []
                logger.info(f"Token exchange granted scopes: {api_scopes}")
            except TokenExchangeError as e:
                # Log but continue - user may still have scopes in original token
                logger.error(f"Token exchange failed: {e}")
        else:
            logger.debug("Token exchange not configured, using original token scopes")

        # Merge API scopes with original claims (API scopes take priority)
        if api_scopes:
            claims["scope"] = " ".join(api_scopes)

        user = User.from_jwt_claims(claims)

        # Step 3: Resolve tenant_id
        tenant_id = None
        tenant_header = request.headers.get("X-Tenant-ID")

        if tenant_header:
            # Use explicit X-Tenant-ID header
            try:
                tenant_id = UUID(tenant_header)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid X-Tenant-ID header format",
                )
        else:
            # No header: resolve user's default organization from DB
            result = await db.execute(
                select(OrganizationMember).where(OrganizationMember.user_id == user.id).limit(1)
            )
            org_member = result.scalar_one_or_none()

            if org_member:
                # Verify organization is active
                result = await db.execute(
                    select(Organization).where(
                        Organization.id == org_member.organization_id,
                        Organization.is_active == True,  # noqa: E712
                    )
                )
                organization = result.scalar_one_or_none()
                if organization:
                    tenant_id = organization.id
                    logger.debug(f"Resolved default tenant {tenant_id} for user {user.id}")

        auth_context = AuthContext(user=user, tenant_id=tenant_id)

        # Store tenant_id in request.state for API tracking middleware
        request.state.tenant_id = auth_context.tenant_id

        return auth_context
    except JWTValidationError as e:
        logger.debug(f"OAuth2 auth failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"OAuth2 auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    oauth2_token: str | None = Depends(get_oauth2_scheme() or (lambda: None)),
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext | None:
    """Get authentication context if present, None otherwise.

    Useful for endpoints that support both authenticated and anonymous access.
    """
    token = await _get_token_from_oauth2_or_bearer(request, oauth2_token, bearer_credentials)

    if not token:
        return None

    try:
        return await get_auth_context(request, db, oauth2_token, bearer_credentials)
    except HTTPException:
        return None


async def get_current_user(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> User:
    """Get the current authenticated user."""
    return auth.user


async def get_optional_user(
    auth: Annotated[AuthContext | None, Depends(get_optional_auth_context)],
) -> User | None:
    """Get the current user if authenticated, None otherwise."""
    if auth:
        return auth.user
    return None


def require_scopes(*required_scopes: str):
    """Dependency factory to require specific scopes.

    Usage:
        @router.get("/data")
        async def get_data(
            auth: AuthContext = Depends(require_scopes("knowledge:read"))
        ):
    """

    async def check_scopes(
        request: Request,
        auth: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> AuthContext:
        for scope in required_scopes:
            auth.require_scope(scope)
        return auth

    return check_scopes


# Type aliases for cleaner dependency injection
Auth = Annotated[AuthContext, Depends(get_auth_context)]
OptionalAuth = Annotated[AuthContext | None, Depends(get_optional_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
