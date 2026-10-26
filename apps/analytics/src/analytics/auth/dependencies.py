# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI dependencies for OAuth2 authentication."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2AuthorizationCodeBearer

from analytics.auth.jwt import TokenRevokedError, jwt_validator
from analytics.auth.models import User
from analytics.auth.token_exchange import TokenExchangeError, token_exchange_client
from analytics.config import settings
from analytics.logging import get_logger

logger = get_logger(__name__)


async def _no_auth() -> str | None:
    """No-op dependency when OAuth2 is not configured."""
    return None


def _get_oauth2_scheme() -> OAuth2AuthorizationCodeBearer | Callable:
    """Create OAuth2 scheme if configured."""
    if not settings.oauth2_issuer:
        return _no_auth

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


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
) -> User:
    """Get the current authenticated user from JWT token.

    Use this dependency for endpoints that require authentication.
    Raises 401 if not authenticated or token is invalid.
    """
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
        logger.info(
            "User authenticated",
            extra={"user_id": str(user.id), "scopes": list(user.scopes) if user.scopes else []},
        )
        return user
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


def require_scopes(*required_scopes: str) -> Callable:
    """Create a dependency that requires specific scopes via token exchange.

    This dependency uses token exchange to validate that the user has been
    granted the required scopes by the auth server. Results are cached in Redis.

    Usage:
        @router.get("/stats")
        async def get_stats(
            user: User = Depends(require_scopes("analytics:read"))
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

                # Validate the token to get user info
                try:
                    claims = await jwt_validator.validate_token_with_introspection(token)
                except Exception:
                    # Use exchanged token claims if original validation fails
                    claims = {"sub": "", "email": None, "name": None}

                return User(
                    id=claims.get("sub", ""),
                    scopes=granted_scopes,
                    email=claims.get("email"),
                    name=claims.get("name"),
                )

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
                            "WWW-Authenticate": (
                                f'Bearer error="insufficient_scope" scope="{" ".join(scopes_list)}"'
                            )
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

        # Verify required scopes from token
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
                    "WWW-Authenticate": (
                        f'Bearer error="insufficient_scope" scope="{" ".join(scopes_list)}"'
                    )
                },
            )

        logger.info(
            "Scope check passed",
            extra={"user_id": str(user.id), "required_scopes": scopes_list},
        )
        return user

    return dependency
