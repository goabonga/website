# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Rate limiting FastAPI dependencies."""

from fastapi import Depends, HTTPException, Request, status

from backend.auth import User
from backend.auth.dependencies import oauth2_scheme
from backend.auth.introspection import introspection_client
from backend.auth.jwks import jwks_manager
from backend.logging import get_logger
from backend.middleware.rate_limit import RateLimiter, get_rate_limiter
from backend.session.dependencies import ChatContext, get_chat_context
from backend.utils.request import get_client_ip

logger = get_logger(__name__)


async def _get_optional_user(
    token: str | None = Depends(oauth2_scheme),
) -> User | None:
    """Get the current user from token, or None if not authenticated."""
    if token is None:
        return None
    if not jwks_manager.is_configured:
        return None
    try:
        claims = await introspection_client.validate_token_with_introspection(token)
        return User.from_jwt_claims(claims)
    except Exception:
        return None


async def check_rate_limit(
    request: Request,
    user: User | None = Depends(_get_optional_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> User | None:
    """
    Dependency that checks rate limit before processing request.

    Raises 429 Too Many Requests if limit exceeded.
    Returns the user (or None) if within limits.
    """
    client_ip = get_client_ip(request)
    user_id = user.id if user else None

    allowed, remaining, reset_seconds = await rate_limiter.check_rate_limit(
        user_id=user_id,
        client_ip=client_ip,
    )

    # Add rate limit headers to response
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = reset_seconds

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={
                "Retry-After": str(reset_seconds),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
            },
        )

    return user


async def check_rate_limit_with_context(
    request: Request,
    context: ChatContext = Depends(get_chat_context),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> ChatContext:
    """
    Dependency that checks rate limit and returns ChatContext.

    This is the preferred dependency for endpoints that support both
    authenticated and anonymous users with session tracking.

    Raises 429 Too Many Requests if limit exceeded.
    Returns ChatContext with user_id OR session_id.
    """
    client_ip = get_client_ip(request)

    allowed, remaining, reset_seconds = await rate_limiter.check_rate_limit(
        user_id=context.user_id,
        client_ip=client_ip,
    )

    # Add rate limit headers to response
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = reset_seconds

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={
                "Retry-After": str(reset_seconds),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
            },
        )

    return context
