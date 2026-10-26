# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI authentication dependencies."""

import logging
from collections.abc import Callable
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2AuthorizationCodeBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.jwt import JWTValidationError, get_jwt_validator
from knowledge.auth.models import User, WebAuthContext
from knowledge.auth.token_exchange import TokenExchangeError, get_token_exchange_client
from knowledge.config import TEMPLATES_DIR, docs_context, get_settings
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


# Cookie names for web auth
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"
ACTIVE_TENANT_COOKIE = "active_tenant_id"
USER_INFO_COOKIE = "user_info"


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


# =============================================================================
# Web Authentication (Cookie-based)
# =============================================================================


def _create_login_redirect(request: Request) -> RedirectResponse:
    """Create redirect to login page with return URL."""
    return_url = request.url.path
    if request.url.query:
        return_url = f"{return_url}?{request.url.query}"
    login_url = f"/auth/login?{urlencode({'redirect': return_url})}"
    return RedirectResponse(url=login_url, status_code=302)


async def get_token_from_cookie(request: Request) -> str | None:
    """Extract access token from cookie."""
    return request.cookies.get(ACCESS_TOKEN_COOKIE)


async def get_current_user_or_redirect(
    request: Request,
) -> User | RedirectResponse:
    """Get current user from cookie or redirect to login.

    For web pages that require authentication.
    Uses token exchange to get API scopes based on user roles.
    """
    token = await get_token_from_cookie(request)

    if not token:
        return _create_login_redirect(request)

    if not settings.oauth2_issuer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth2 issuer not configured",
        )

    try:
        jwt_validator = get_jwt_validator()
        # Fetch userinfo to get name, email, etc.
        claims = await jwt_validator.validate_token_with_introspection(token, fetch_userinfo=True)

        # Use token exchange to get API scopes based on user roles
        api_scopes: list[str] = []
        if settings.oauth2_client_id and settings.oauth2_client_secret:
            try:
                token_exchange_client = get_token_exchange_client()
                # Exchange token requesting all Knowledge API scopes
                exchange_result = await token_exchange_client.exchange_token(
                    token, requested_scopes=KNOWLEDGE_API_SCOPES
                )
                scope_str = exchange_result.get("scope", "")
                api_scopes = scope_str.split() if scope_str else []
                logger.debug(f"Token exchange granted scopes: {api_scopes}")
            except TokenExchangeError as e:
                logger.warning(f"Token exchange failed: {e}")

        # Merge API scopes with original claims
        if api_scopes:
            claims["scope"] = " ".join(api_scopes)

        return User.from_jwt_claims(claims)
    except Exception as e:
        logger.debug(f"Cookie auth failed: {e}")
        return _create_login_redirect(request)


async def get_web_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WebAuthContext | RedirectResponse:
    """Get web authentication context with tenant resolution.

    For web pages that need both user and tenant context.
    """
    from knowledge.models import Organization, OrganizationMember

    user_result = await get_current_user_or_redirect(request)
    if isinstance(user_result, RedirectResponse):
        return user_result

    user = user_result

    # Get active organization from cookie (still uses tenant cookie name for backward compat)
    active_org_id = request.cookies.get(ACTIVE_TENANT_COOKIE)

    organization = None
    org_member = None

    if active_org_id:
        try:
            org_uuid = UUID(active_org_id)
            # Verify user is member of this organization
            result = await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org_uuid,
                    OrganizationMember.user_id == user.id,
                )
            )
            org_member = result.scalar_one_or_none()

            if org_member:
                result = await db.execute(
                    select(Organization).where(
                        Organization.id == org_uuid,
                        Organization.is_active == True,  # noqa: E712
                    )
                )
                organization = result.scalar_one_or_none()
        except ValueError:
            pass

    # If no active organization, try to find user's first organization
    if not organization:
        result = await db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id).limit(1)
        )
        org_member = result.scalar_one_or_none()

        if org_member:
            result = await db.execute(
                select(Organization).where(
                    Organization.id == org_member.organization_id,
                    Organization.is_active == True,  # noqa: E712
                )
            )
            organization = result.scalar_one_or_none()

    return WebAuthContext(
        user=user,
        tenant=organization,  # Backward compat: tenant alias for organization
        tenant_member=org_member,  # Backward compat: tenant_member alias
    )


def require_scope_or_redirect(required_scope: str) -> Callable:
    """Dependency factory that requires a scope or redirects to 403.

    For web pages that need scope checking with HTML error page.
    """

    async def check_scope(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> WebAuthContext | Response:
        from fastapi.templating import Jinja2Templates

        auth_result = await get_web_auth_context(request, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        if not auth_result.has_scope(required_scope):
            # Return 403 page
            templates = Jinja2Templates(directory=TEMPLATES_DIR, context_processors=[docs_context])
            return templates.TemplateResponse(
                request,
                "errors/403.html",
                {
                    "user": auth_result.user,
                    "required_scope": required_scope,
                },
                status_code=403,
            )

        return auth_result

    return check_scope


def require_resource_scopes_or_redirect(
    resource: str, extra_scopes: list[str] | None = None
) -> Callable:
    """Dependency factory that requires read/write/delete scopes for a resource.

    For web pages that need full CRUD access to a resource.
    """

    async def check_scopes(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> WebAuthContext | Response:
        auth_result = await get_web_auth_context(request, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        # Check resource scopes
        required_scopes = [f"{resource}:read", f"{resource}:write"]
        if extra_scopes:
            required_scopes.extend(extra_scopes)

        for scope in required_scopes:
            if not auth_result.has_scope(scope):
                from fastapi.templating import Jinja2Templates

                templates = Jinja2Templates(
                    directory=TEMPLATES_DIR, context_processors=[docs_context]
                )
                return templates.TemplateResponse(
                    request,
                    "errors/403.html",
                    {
                        "user": auth_result.user,
                        "required_scope": scope,
                    },
                    status_code=403,
                )

        return auth_result

    return check_scopes


def require_tenant_admin() -> Callable:
    """Dependency factory that requires tenant admin privileges.

    For web pages that need admin access to the tenant.
    """

    async def check_admin(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> WebAuthContext | Response:
        auth_result = await get_web_auth_context(request, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        if not auth_result.is_tenant_admin:
            from fastapi.templating import Jinja2Templates

            templates = Jinja2Templates(directory=TEMPLATES_DIR, context_processors=[docs_context])
            return templates.TemplateResponse(
                request,
                "errors/403.html",
                {
                    "user": auth_result.user,
                    "required_scope": "tenant:admin",
                },
                status_code=403,
            )

        return auth_result

    return check_admin


# Type aliases for cleaner dependency injection
Auth = Annotated[AuthContext, Depends(get_auth_context)]
OptionalAuth = Annotated[AuthContext | None, Depends(get_optional_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
WebAuth = Annotated[WebAuthContext | RedirectResponse, Depends(get_web_auth_context)]
