# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI dependencies for OAuth2 authentication."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2AuthorizationCodeBearer

from mailler.auth.introspection import TokenRevokedError, introspection_client
from mailler.auth.jwks import jwks_manager
from mailler.auth.models import User
from mailler.auth.token_exchange import TokenExchangeError, token_exchange_client
from mailler.config import settings
from mailler.logging import get_logger, set_request_context

logger = get_logger(__name__)


def _is_jwt_token(token: str) -> bool:
    """Check if a token looks like a JWT (3 base64url segments separated by dots).

    PersonalAccessTokens and other opaque tokens do not have this structure.
    """
    parts = token.split(".")
    return len(parts) == 3 and all(len(part) > 0 for part in parts)


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
    """Authentication context for API requests.

    Besides the authenticated user it carries the client the call is made on
    behalf of: every resource belongs to one client and a caller only sees the
    resources of its own client, unless it holds the administration scope.
    """

    def __init__(self, user: User, is_admin: bool = False) -> None:
        self.user = user
        self.is_admin = is_admin

    @property
    def client_id(self) -> str | None:
        """Get the OAuth2 client the token was issued to."""
        return self.user.client_id

    def require_client_id(self) -> str:
        """Return the caller's client identifier, raising 403 when the token has none."""
        if not self.user.client_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token carries no client identity",
            )
        return self.user.client_id

    def target_client_id(self, requested: str | None = None) -> str:
        """Resolve the client a call acts on.

        Without ``requested`` this is the caller's own client. Naming another
        client is reserved to administrators; anyone else gets ``403``.
        """
        if requested is None or requested == self.user.client_id:
            return self.require_client_id()
        if not self.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can act on another client",
            )
        return requested

    def owns(self, owner_client_id: str | None) -> bool:
        """Tell whether a resource owned by ``owner_client_id`` is visible to the caller."""
        return self.is_admin or (
            self.user.client_id is not None and owner_client_id == self.user.client_id
        )

    def restrict(self, stmt, column, client_id: str | None = None):
        """Restrict a query on a client-owned table to the resources the caller may see.

        Regular callers always get their own client; administrators get every
        client unless ``client_id`` narrows the query down to one of them.
        """
        if self.is_admin:
            return stmt.where(column == client_id) if client_id else stmt
        if client_id is not None and client_id != self.user.client_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can query another client",
            )
        return stmt.where(column == self.require_client_id())

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


def _build_context(request: Request, user: User, is_admin: bool) -> AuthContext:
    """Build the context of an authenticated call and expose it to logging."""
    if not is_admin and not user.client_id:
        logger.info("Token without client identity refused")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token carries no client identity",
        )
    set_request_context(user_id=str(user.id), client_id=user.client_id)
    request.state.user_id = str(user.id)
    request.state.client_id = user.client_id
    return AuthContext(user=user, is_admin=is_admin)


async def _holds_admin_scope(token: str, user: User, original_scopes: list[str]) -> bool:
    """Tell whether the caller holds the administration scope.

    The scope has to be present in the validated token and, when token exchange
    is configured for JWTs, to be granted by the authorization server too.
    """
    if not User(id=user.id, scopes=original_scopes).has_scope(settings.admin_scope):
        return False
    if not (_is_jwt_token(token) and token_exchange_client.is_configured):
        return True
    try:
        await token_exchange_client.validate_token_scopes(token, [settings.admin_scope])
    except TokenExchangeError:
        return False
    return True


async def get_auth_context(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> AuthContext:
    """Extract and validate authentication from request.

    Supports:
    - OAuth2 Authorization Code flow (Swagger UI with PKCE)
    - Authorization: Bearer <jwt_token> (API clients)
    - Authorization: Bearer <opaque_token> (PersonalAccessTokens)
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
        if _is_jwt_token(token):
            claims = await introspection_client.validate_token_with_introspection(token)
        else:
            logger.debug("Opaque token detected, using introspection-only validation")
            claims = await introspection_client.validate_opaque_token(token)

        user = User.from_jwt_claims(claims)
        is_admin = await _holds_admin_scope(token, user, user.scopes)
        return _build_context(request, user, is_admin)
    except HTTPException:
        raise
    except TokenRevokedError:
        logger.info("Token revoked - access denied")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )
    except Exception as e:
        logger.info("Invalid token: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )


async def get_current_user(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> User:
    """Get the current authenticated user."""
    return auth.user


def require_scopes(*required_scopes: str) -> Callable:
    """Create a dependency that requires specific scopes via token exchange.

    Uses token exchange to validate that the user has been granted the
    required scopes by the auth server. Results are cached in Redis.

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

        is_jwt = _is_jwt_token(token)

        # Token exchange only works with JWT tokens, not opaque tokens (PATs)
        if is_jwt and token_exchange_client.is_configured and scopes_list:
            try:
                result = await token_exchange_client.validate_token_scopes(token, scopes_list)

                granted_scopes = result.get("scope", "").split()

                # The caller's identity always comes from the original token: the
                # exchanged token is issued to this service, not to the calling client.
                try:
                    claims = await introspection_client.validate_token_with_introspection(token)
                except Exception as e:
                    logger.warning("Token validation failed after exchange: %s", e)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token validation failed",
                        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
                    )

                user = User.from_jwt_claims(claims)
                original_scopes = user.scopes
                user.scopes = granted_scopes
                is_admin = await _holds_admin_scope(token, user, original_scopes)
                return _build_context(request, user, is_admin)

            except HTTPException:
                raise
            except TokenExchangeError as e:
                logger.info("Token exchange failed: %s", e)
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

        # Direct validation: for opaque tokens (PATs) or when token exchange is not configured
        if not is_jwt:
            logger.debug("Opaque token detected, skipping token exchange, using introspection")

        try:
            if is_jwt:
                claims = await introspection_client.validate_token_with_introspection(token)
            else:
                claims = await introspection_client.validate_opaque_token(token)
        except TokenRevokedError:
            logger.info("Token revoked - access denied (scope check)")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
        except Exception as e:
            logger.info("Invalid token (scope check): %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        user = User.from_jwt_claims(claims)

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

        is_admin = await _holds_admin_scope(token, user, user.scopes)
        return _build_context(request, user, is_admin)

    return dependency


# Type aliases for cleaner dependency injection
Auth = Annotated[AuthContext, Depends(get_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]
