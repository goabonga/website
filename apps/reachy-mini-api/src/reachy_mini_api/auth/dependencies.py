# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI dependencies for OAuth2 authentication."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2AuthorizationCodeBearer

from reachy_mini_api.auth.jwks import jwks_manager
from reachy_mini_api.auth.models import User
from reachy_mini_api.config import settings
from reachy_mini_api.logging import get_logger, set_request_context

logger = get_logger(__name__)


async def _extract_bearer_token(request: Request) -> str | None:
    """Extract bearer token from Authorization header (fallback when OAuth2 scheme is not configured)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


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


# OAuth2 scheme for Swagger UI integration, or simple bearer extraction
oauth2_scheme = _get_oauth2_scheme() or _extract_bearer_token


class AuthContext:
    """Authentication context for API requests."""

    def __init__(self, user: User) -> None:
        self.user = user

    @property
    def user_id(self) -> str:
        """Get user ID as string."""
        return str(self.user.id)

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


def _set_request_identity(request: Request, claims: dict, user: User) -> None:
    """Expose the authenticated identity to the request and to structured logging."""
    client_id = claims.get("client_id") or claims.get("azp")
    set_request_context(user_id=str(user.id), client_id=client_id)
    request.state.user_id = str(user.id)
    request.state.client_id = client_id


async def get_auth_context(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> AuthContext:
    """Extract and validate authentication from request.

    Supports:
    - OAuth2 Authorization Code flow (Swagger UI with PKCE)
    - Authorization: Bearer <jwt_token> (API clients)
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not jwks_manager.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth2 not configured",
        )

    try:
        claims = await jwks_manager.validate_token(token)
        user = User.from_jwt_claims(claims)
    except Exception as e:
        logger.info("Invalid token: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    _set_request_identity(request, claims, user)
    return AuthContext(user=user)


async def get_current_user(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> User:
    """Get the current authenticated user."""
    return auth.user


def require_scopes(*required_scopes: str) -> Callable:
    """Create a dependency that requires specific scopes.

    The token signature is validated against the issuer JWKS and the scopes
    carried by the token are checked, with wildcard support.

    Usage:
        @router.get("/resource")
        async def get_resource(
            auth: AuthContext = Depends(require_scopes("resource:read"))
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
    ) -> AuthContext:
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not jwks_manager.is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OAuth2 not configured",
            )

        try:
            claims = await jwks_manager.validate_token(token)
            user = User.from_jwt_claims(claims)
        except Exception as e:
            logger.info("Invalid token (scope check): %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        # Verify required scopes with wildcard support
        missing_scopes = [s for s in scopes_list if not user.has_scope(s)]
        if missing_scopes:
            logger.info(
                "Insufficient scopes",
                extra={
                    "user_id": str(user.id),
                    "missing_scopes": missing_scopes,
                    "required_scopes": scopes_list,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scopes. Missing: {', '.join(missing_scopes)}",
                headers={
                    "WWW-Authenticate": f'Bearer error="insufficient_scope" scope="{" ".join(scopes_list)}"'
                },
            )

        _set_request_identity(request, claims, user)
        return AuthContext(user=user)

    return dependency


# Type aliases for cleaner dependency injection
Auth = Annotated[AuthContext, Depends(get_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]
