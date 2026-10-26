# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI authentication dependencies with scope-based authorization.

Supports two authentication methods:
1. Bearer token (for API calls): Authorization: Bearer <access_token>
2. Cookie (for HTML pages): access_token cookie set after OAuth2 login
"""

import json
import logging
import secrets
from collections.abc import Callable
from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.jwt import TokenRevokedError, jwt_validator
from internal.auth.models import User
from internal.config import settings
from internal.services.token_exchange import TokenExchangeError, token_exchange_client

logger = logging.getLogger(__name__)

# Templates for HTML error pages
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Scopes gating links of the admin sidebar (admin/base.html). Every HTML page
# renders the sidebar, so every page must obtain them through its token
# exchange: the access token itself only carries the OIDC scopes.
SIDEBAR_SCOPES = ("vpn:admin", "billing:read")


def _with_sidebar_scopes(scopes: list[str]) -> list[str]:
    """Return the scopes to request, with the sidebar scopes appended once."""
    return list(dict.fromkeys([*scopes, *SIDEBAR_SCOPES]))


# Pending token refresh to be applied via middleware
_pending_token_refresh: dict | None = None


def _get_oauth2_scheme() -> OAuth2AuthorizationCodeBearer | None:
    """Create OAuth2 scheme if configured."""
    if not settings.oauth2_issuer:
        return None

    issuer = settings.oauth2_issuer.rstrip("/")
    return OAuth2AuthorizationCodeBearer(
        authorizationUrl=f"{issuer}/oauth2/authorize",
        tokenUrl=f"{issuer}/oauth2/token",
        scopes={
            "openid": "OpenID Connect",
            "profile": "User profile",
            "email": "User email",
        },
        auto_error=False,
    )


# OAuth2 scheme for Swagger UI integration
oauth2_scheme = _get_oauth2_scheme()

# Cookie names
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"
USER_INFO_COOKIE = "user_info"


def _get_user_info_from_cookie(request: Request) -> dict | None:
    """Extract user info from cookie if present."""
    user_info_cookie = request.cookies.get(USER_INFO_COOKIE)
    if user_info_cookie:
        try:
            return json.loads(user_info_cookie)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


async def _try_refresh_token(refresh_token: str) -> dict | None:
    """Attempt to refresh the access token using the refresh token.

    Returns token data dict on success, None on failure.
    """
    if not settings.oauth2_issuer:
        return None

    issuer = settings.oauth2_issuer.rstrip("/")
    token_url = f"{issuer}/oauth2/token"

    try:
        async with httpx.AsyncClient() as client:
            # Use the public frontend client (no client_secret for public clients)
            response = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.oauth2_frontend_client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )

            if response.status_code == 200:
                tokens = response.json()
                logger.info("Successfully refreshed access token")
                return tokens
            else:
                logger.warning("Token refresh failed: %s", response.status_code)
                return None

    except httpx.RequestError as e:
        logger.error("Token refresh request failed: %s", e)
        return None


async def get_token_from_request(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> str | None:
    """Extract access token from Bearer header or cookie."""
    # Try Bearer token first (from oauth2_scheme)
    if token is not None:
        return token

    # Fall back to cookie
    return request.cookies.get(ACCESS_TOKEN_COOKIE)


def get_current_access_token(request: Request, token: str | None) -> str | None:
    """Get the current access token, preferring refreshed token if available.

    This should be used after get_current_user_or_redirect to ensure we use
    the refreshed token for subsequent operations like token exchange.
    """
    # If a token was refreshed during this request, use the new one
    if _pending_token_refresh and _pending_token_refresh.get("access_token"):
        return _pending_token_refresh["access_token"]

    # Otherwise use the token from the request
    if token is not None:
        return token

    return request.cookies.get(ACCESS_TOKEN_COOKIE)


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> User:
    """Get the current authenticated user from JWT token.

    Checks Bearer header first, then falls back to cookie.
    Raises 401 if not authenticated or token is invalid.
    """
    token = await get_token_from_request(request, token)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not settings.oauth2_issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth2 not configured",
        )

    try:
        claims = await jwt_validator.validate_token_with_introspection(token)
        user = User.from_jwt_claims(claims)
        logger.debug("Authenticated user: %s with scopes: %s", user.id, user.scopes)
        return user
    except TokenRevokedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )
    except Exception as e:
        logger.debug("Invalid token: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )


async def get_current_user_or_redirect(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> User | RedirectResponse:
    """Get the current user or redirect to login for HTML pages.

    For HTML pages, instead of returning 401, redirects to OAuth2 login.
    Attempts to refresh the token if expired but refresh token is available.
    """
    global _pending_token_refresh

    token = await get_token_from_request(request, token)
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)

    # No access token - try to refresh if we have a refresh token
    if token is None:
        if refresh_token:
            logger.debug("No access token, attempting refresh")
            tokens = await _try_refresh_token(refresh_token)
            if tokens and tokens.get("access_token"):
                token = tokens["access_token"]
                # Store pending refresh to set cookies in middleware
                _pending_token_refresh = tokens
            else:
                return _create_login_redirect(request)
        else:
            return _create_login_redirect(request)

    if not settings.oauth2_issuer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not configured",
        )

    try:
        claims = await jwt_validator.validate_token_with_introspection(token)
        user = User.from_jwt_claims(claims)

        # Enrich user with info from user_info cookie (set during login)
        user_info = _get_user_info_from_cookie(request)
        if user_info:
            if not user.name and user_info.get("name"):
                user.name = user_info["name"]
            if not user.email and user_info.get("email"):
                user.email = user_info["email"]

        logger.debug("Authenticated user: %s with scopes: %s", user.id, user.scopes)
        return user
    except Exception as e:
        logger.debug("Token invalid or expired: %s", e)
        # Try to refresh the token before redirecting to login
        if refresh_token:
            logger.debug("Attempting token refresh after validation failure")
            tokens = await _try_refresh_token(refresh_token)
            if tokens and tokens.get("access_token"):
                # Validate the new token
                try:
                    claims = await jwt_validator.validate_token_with_introspection(
                        tokens["access_token"]
                    )
                    user = User.from_jwt_claims(claims)

                    # Enrich user with info from user_info cookie
                    user_info = _get_user_info_from_cookie(request)
                    if user_info:
                        if not user.name and user_info.get("name"):
                            user.name = user_info["name"]
                        if not user.email and user_info.get("email"):
                            user.email = user_info["email"]

                    # Store pending refresh to set cookies in middleware
                    _pending_token_refresh = tokens
                    logger.info("Token refreshed successfully")
                    return user
                except Exception as refresh_error:
                    logger.warning("Refreshed token validation failed: %s", refresh_error)

        return _create_login_redirect(request)


def _create_login_redirect(request: Request) -> RedirectResponse:
    """Create a redirect to OAuth2 authorization endpoint."""
    state = secrets.token_urlsafe(32)
    # Store the original URL to redirect back after login
    original_url = str(request.url)

    # Build authorization URL using the public frontend client (PKCE)
    # Only request basic OIDC scopes - elevated scopes are obtained via token exchange
    issuer = settings.oauth2_issuer.rstrip("/")
    params = {
        "client_id": settings.oauth2_frontend_client_id,
        "response_type": "code",
        "redirect_uri": f"{settings.app_base_url}/auth/callback",
        "scope": "openid profile email offline_access",
        "state": state,
    }
    auth_url = f"{issuer}/oauth2/authorize?{urlencode(params)}"

    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    # Store state and original URL in cookies for callback verification
    response.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        "oauth_redirect",
        original_url,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


def require_scope(required_scope: str) -> Callable:
    """Dependency factory that requires a specific scope (no token exchange).

    Usage:
        @router.get("/admin")
        async def admin_page(user: User = Depends(require_scope("internal:admin"))):
            ...
    """

    async def dependency(
        user: User = Depends(get_current_user),
    ) -> User:
        if not user.has_scope(required_scope):
            logger.warning(
                "User %s denied access - missing scope %s (has: %s)",
                user.id,
                required_scope,
                user.scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}",
            )
        return user

    return dependency


def require_scopes(*required_scopes: str) -> Callable:
    """Create a dependency that requires specific scopes via token exchange.

    This dependency uses token exchange to validate that the user has been
    granted the required scopes by the auth server. Results are cached in Redis.

    Usage:
        @router.get("/admin/users")
        async def list_users(
            user: User = Depends(require_scopes("users:read"))
        ):
            ...

    Args:
        *required_scopes: Scopes required to access the route

    Returns:
        FastAPI dependency function
    """
    scopes_list = list(required_scopes)

    async def dependency(
        request: Request,
        token: str | None = Depends(oauth2_scheme),
    ) -> User:
        if not settings.oauth2_issuer:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OAuth2 not configured",
            )

        token = await get_token_from_request(request, token)

        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # If token exchange is enabled, use it to validate scopes
        if token_exchange_client.is_configured and scopes_list:
            try:
                result = await token_exchange_client.validate_token_scopes(token, scopes_list)

                # Get scopes from exchange result
                granted_scopes = result.get("scope", "").split()

                # Validate the token to get user info and original scopes
                try:
                    claims = await jwt_validator.validate_token_with_introspection(token)
                    # Get original scopes from token to preserve wildcards (e.g., "*")
                    original_scope_str = claims.get("scope", "")
                    original_scopes = original_scope_str.split() if original_scope_str else []
                except Exception:
                    # Use minimal claims if original validation fails
                    claims = {"sub": "", "email": None, "name": None}
                    original_scopes = []

                # Merge granted scopes with original scopes to preserve wildcards
                merged_scopes = list(set(original_scopes) | set(granted_scopes))

                return User(
                    id=claims.get("sub", ""),
                    scopes=merged_scopes,
                    email=claims.get("email"),
                    name=claims.get("name"),
                )

            except TokenExchangeError as e:
                logger.warning(f"Token exchange failed: {e}")
                if e.error_code == "invalid_grant":
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired token",
                        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
                    )
                elif e.error_code == "insufficient_scope":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient scopes. Required: {', '.join(scopes_list)}",
                        headers={
                            "WWW-Authenticate": f'Bearer error="insufficient_scope" scope="{" ".join(scopes_list)}"'
                        },
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=str(e),
                        headers={"WWW-Authenticate": "Bearer"},
                    )

        # Fallback: validate token directly without token exchange
        try:
            claims = await jwt_validator.validate_token_with_introspection(token)
        except TokenRevokedError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
        except Exception as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        user = User.from_jwt_claims(claims)

        # Verify required scopes from token
        missing_scopes = [s for s in scopes_list if not user.has_scope(s)]
        if missing_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scopes. Missing: {', '.join(missing_scopes)}",
                headers={
                    "WWW-Authenticate": f'Bearer error="insufficient_scope" scope="{" ".join(scopes_list)}"'
                },
            )

        return user

    return dependency


def _render_403_page(
    request: Request,
    required_scope: str | None = None,
    detail: str | None = None,
) -> HTMLResponse:
    """Render a 403 Forbidden HTML page."""
    return templates.TemplateResponse(
        request=request,
        name="errors/403.html",
        context={
            "request": request,
            "required_scope": required_scope,
            "detail": detail,
        },
        status_code=status.HTTP_403_FORBIDDEN,
    )


def require_scope_or_redirect(required_scope: str) -> Callable:
    """Dependency factory for HTML pages that requires a specific scope.

    Uses token exchange to validate scopes. Redirects to login if not authenticated,
    returns 403 HTML page if scope validation fails.
    """

    async def dependency(
        request: Request,
        token: str | None = Depends(oauth2_scheme),
    ) -> User | RedirectResponse | HTMLResponse:
        result = await get_current_user_or_redirect(request, token)

        if isinstance(result, RedirectResponse):
            return result

        user = result

        # Use token exchange to validate the required scope
        if token_exchange_client.is_configured:
            # Use refreshed token if available (important after token refresh)
            access_token = get_current_access_token(request, token)
            if access_token:
                try:
                    exchange_result = await token_exchange_client.validate_token_scopes(
                        access_token, _with_sidebar_scopes([required_scope])
                    )
                    # Merge granted scopes with original scopes to preserve wildcards
                    # This allows super_admin with "*" to retain full access
                    granted_scopes = exchange_result.get("scope", "").split()
                    original_scopes = set(user.scopes)
                    merged_scopes = list(original_scopes | set(granted_scopes))
                    user.scopes = merged_scopes
                    logger.debug(
                        "Token exchange granted scopes for user %s: %s (merged: %s)",
                        user.id,
                        granted_scopes,
                        merged_scopes,
                    )
                    # The exchange may grant only the sidebar scopes
                    if not user.has_scope(required_scope):
                        return _render_403_page(
                            request,
                            required_scope=required_scope,
                            detail=f"Missing required scope: {required_scope}",
                        )
                    return user
                except TokenExchangeError as e:
                    logger.warning(
                        "Token exchange failed for user %s - scope %s: %s",
                        user.id,
                        required_scope,
                        e,
                    )
                    if e.error_code == "insufficient_scope":
                        return _render_403_page(
                            request,
                            required_scope=required_scope,
                            detail=f"Missing required scope: {required_scope}",
                        )
                    return _render_403_page(
                        request,
                        required_scope=required_scope,
                        detail=f"Scope validation failed: {e}",
                    )

        # Fallback: check scopes from JWT token directly
        if not user.has_scope(required_scope):
            logger.warning(
                "User %s denied access - missing scope %s (has: %s)",
                user.id,
                required_scope,
                user.scopes,
            )
            return _render_403_page(
                request,
                required_scope=required_scope,
                detail=f"Missing required scope: {required_scope}",
            )
        return user

    return dependency


def require_resource_scopes_or_redirect(
    resource: str,
    required_scope: str | None = None,
    extra_scopes: list[str] | None = None,
) -> Callable:
    """Dependency factory for HTML pages that requests all scopes for a resource.

    This requests read, write, and delete scopes for the resource in a single
    token exchange. This ensures the user object has all granted scopes for
    proper button visibility in templates (edit, delete buttons, etc.).

    The required_scope parameter specifies the minimum scope needed to access
    the page. If not provided, defaults to "{resource}:read".

    The extra_scopes parameter allows requesting additional scopes that are not
    required but should be checked (e.g., analytics:read for dashboard display).

    Usage:
        require_knowledge = require_resource_scopes_or_redirect("knowledge")

        # With extra scopes for optional features
        require_dashboard = require_resource_scopes_or_redirect(
            "conversations", extra_scopes=["analytics:read"]
        )

        @router.get("")
        async def list_knowledge(
            auth_result = Depends(require_knowledge),
        ):
            ...
    """
    min_scope = required_scope or f"{resource}:read"
    all_scopes = [f"{resource}:read", f"{resource}:write", f"{resource}:delete"]
    if extra_scopes:
        all_scopes.extend(extra_scopes)
    all_scopes = _with_sidebar_scopes(all_scopes)

    async def dependency(
        request: Request,
        token: str | None = Depends(oauth2_scheme),
    ) -> User | RedirectResponse | HTMLResponse:
        result = await get_current_user_or_redirect(request, token)

        if isinstance(result, RedirectResponse):
            return result

        user = result

        # Use token exchange to validate and get all resource scopes
        if token_exchange_client.is_configured:
            # Use refreshed token if available (important after token refresh)
            access_token = get_current_access_token(request, token)
            if access_token:
                try:
                    # Request all scopes for the resource at once
                    exchange_result = await token_exchange_client.validate_token_scopes(
                        access_token, all_scopes
                    )
                    # Merge granted scopes with original scopes to preserve wildcards
                    granted_scopes = exchange_result.get("scope", "").split()
                    original_scopes = set(user.scopes)
                    merged_scopes = list(original_scopes | set(granted_scopes))
                    user.scopes = merged_scopes
                    logger.debug(
                        "Token exchange granted resource scopes for user %s: %s (merged: %s)",
                        user.id,
                        granted_scopes,
                        merged_scopes,
                    )

                    # Check if user has minimum required scope
                    if not user.has_scope(min_scope):
                        return _render_403_page(
                            request,
                            required_scope=min_scope,
                            detail=f"Missing required scope: {min_scope}",
                        )
                    return user
                except TokenExchangeError as e:
                    logger.warning(
                        "Token exchange failed for user %s - resource %s: %s",
                        user.id,
                        resource,
                        e,
                    )
                    if e.error_code == "insufficient_scope":
                        return _render_403_page(
                            request,
                            required_scope=min_scope,
                            detail=f"Missing required scope: {min_scope}",
                        )
                    return _render_403_page(
                        request,
                        required_scope=min_scope,
                        detail=f"Scope validation failed: {e}",
                    )

        # Fallback: check scopes from JWT token directly
        if not user.has_scope(min_scope):
            logger.warning(
                "User %s denied access - missing scope %s (has: %s)",
                user.id,
                min_scope,
                user.scopes,
            )
            return _render_403_page(
                request,
                required_scope=min_scope,
                detail=f"Missing required scope: {min_scope}",
            )
        return user

    return dependency


def require_any_scope(*required_scopes: str) -> Callable:
    """Dependency factory that requires any of the specified scopes.

    Usage:
        @router.get("/data")
        async def get_data(user: User = Depends(require_any_scope("internal:read", "internal:admin"))):
            ...
    """

    async def dependency(
        user: User = Depends(get_current_user),
    ) -> User:
        if not user.has_any_scope(list(required_scopes)):
            logger.warning(
                "User %s denied access - missing scopes %s (has: %s)",
                user.id,
                required_scopes,
                user.scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope. Need one of: {', '.join(required_scopes)}",
            )
        return user

    return dependency


async def get_exchanged_token(
    request: Request,
    scopes: list[str],
    token: str | None = Depends(oauth2_scheme),
) -> str:
    """Exchange the user's token for one with elevated scopes.

    This dependency extracts the user's access token and exchanges it
    for a new token with the requested admin scopes using RFC 8693.

    Args:
        request: The FastAPI request.
        scopes: List of scopes to request in the exchanged token.
        token: Optional Bearer token from OAuth2 scheme.

    Returns:
        The exchanged access token string.

    Raises:
        HTTPException: If not authenticated or token exchange fails.
    """
    token = await get_token_from_request(request, token)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        result = await token_exchange_client.exchange_token(
            subject_token=token,
            requested_scopes=scopes,
        )
        return result["access_token"]
    except TokenExchangeError as e:
        logger.error("Token exchange failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token exchange failed: {e}",
        )
    except Exception as e:
        logger.error("Token exchange configuration error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token exchange not configured",
        )


def require_exchanged_token(*scopes: str):
    """Dependency factory that exchanges the user token for admin scopes.

    Usage:
        @router.get("/admin/users")
        async def list_users(
            admin_token: str = Depends(require_exchanged_token("users:read")),
        ):
            # Use admin_token to call auth API
            ...
    """

    async def dependency(
        request: Request,
        token: str | None = Depends(oauth2_scheme),
    ) -> str:
        return await get_exchanged_token(request, list(scopes), token)

    return dependency


def get_pending_token_refresh() -> dict | None:
    """Get pending token refresh data (for middleware to set cookies)."""
    return _pending_token_refresh


def clear_pending_token_refresh() -> None:
    """Clear pending token refresh data after cookies are set."""
    global _pending_token_refresh
    _pending_token_refresh = None
