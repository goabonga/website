# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Session dependencies for FastAPI."""

import uuid
from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import oauth2_scheme
from backend.auth.introspection import introspection_client
from backend.auth.jwks import jwks_manager
from backend.auth.models import User
from backend.database import get_db
from backend.logging import get_logger
from backend.middleware.rate_limit import RateLimiter, get_rate_limiter
from backend.session.service import SessionService
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


@dataclass
class ChatContext:
    """Unified context for chat requests (authenticated or anonymous).

    Provides a consistent interface for handling both authenticated users
    (via JWT) and anonymous users (via httpOnly cookie).

    Session priority:
    1. JWT authentication (authenticated user)
    2. httpOnly cookie (session_id cookie)
    3. Auto-create new session (rate-limited by IP)
    """

    user_id: uuid.UUID | str | None
    session_id: str | None
    is_authenticated: bool
    session_created: bool = False  # True if session was auto-created
    client_ip: str = ""  # Client IP for rate limiting
    access_token: str | None = None  # JWT token for auth service calls
    anonymous_session_id: str | None = None  # Anonymous session to migrate on login
    scopes: set[str] | None = None  # User scopes from JWT (for tool filtering)

    @property
    def owner_id(self) -> str | None:
        """Get the owner identifier (user_id or session_id)."""
        if self.user_id:
            return str(self.user_id)
        return self.session_id


def _validate_session_id(session_id: str | None, source: str) -> str | None:
    """Validate session ID format (must be UUID)."""
    if not session_id:
        return None
    try:
        uuid.UUID(session_id)
        return session_id
    except ValueError:
        logger.warning(
            "Invalid session ID from %s: %s", source, session_id[:8] if session_id else "empty"
        )
        return None


async def get_chat_context(
    request: Request,
    user: User | None = Depends(_get_optional_user),
    token: str | None = Depends(oauth2_scheme),
    session_id_cookie: str | None = Cookie(None, alias="session_id"),
    db: AsyncSession = Depends(get_db),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> ChatContext:
    """Get unified chat context for authenticated or anonymous users.

    Priority:
    1. If JWT is valid -> authenticated user (session ignored)
    2. If httpOnly cookie present -> use cookie session
    3. Otherwise -> auto-create session (rate-limited by IP)

    Args:
        request: FastAPI request
        user: Optional authenticated user from JWT
        token: Optional bearer token (for token forwarding)
        session_id_cookie: Optional session ID from httpOnly cookie
        db: Database session
        rate_limiter: Rate limiter for session creation

    Returns:
        ChatContext with user_id OR session_id
    """
    client_ip = get_client_ip(request)
    access_token = token

    # 1. Authenticated user takes priority
    if user:
        # Check if there's an anonymous session cookie to migrate
        anonymous_session = _validate_session_id(session_id_cookie, "cookie")
        if anonymous_session:
            logger.info(
                "ChatContext: authenticated user with anonymous session to migrate",
                extra={"user_id": str(user.id), "session_id": anonymous_session[:8]},
            )
        else:
            logger.info("ChatContext: authenticated user", extra={"user_id": str(user.id)})
        return ChatContext(
            user_id=user.id,
            session_id=None,
            is_authenticated=True,
            client_ip=client_ip,
            access_token=access_token,
            anonymous_session_id=anonymous_session,
            scopes=set(user.scopes) if user.scopes else None,
        )

    # 2. Check cookie (secure httpOnly cookie)
    session_id = _validate_session_id(session_id_cookie, "cookie")

    # 3. Use existing session if provided
    if session_id:
        session_service = SessionService(db)
        try:
            existing = await session_service.get(session_id)
            if existing:
                logger.info(
                    "ChatContext: anonymous session",
                    extra={"session_id": session_id[:8], "client_ip": client_ip},
                )
                return ChatContext(
                    user_id=None,
                    session_id=session_id,
                    is_authenticated=False,
                    client_ip=client_ip,
                )
            # Session ID provided but doesn't exist - treat as new session request
            # Check rate limit before creating
            allowed, _, reset_seconds = await rate_limiter.check_session_creation_limit(client_ip)
            if not allowed:
                logger.info(
                    "Session creation rate limit exceeded",
                    extra={"session_id": session_id[:8], "client_ip": client_ip},
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Session creation limit exceeded. Please try again later.",
                    headers={"Retry-After": str(reset_seconds)},
                )
            await session_service.create(session_id)
            await rate_limiter.record_session_creation(client_ip)
            logger.info(
                "ChatContext: created session from provided ID",
                extra={"session_id": session_id[:8], "client_ip": client_ip},
            )
            return ChatContext(
                user_id=None,
                session_id=session_id,
                is_authenticated=False,
                session_created=True,
                client_ip=client_ip,
            )
        finally:
            await session_service.close()

    # 5. No session provided -> auto-create (rate-limited)
    allowed, _, reset_seconds = await rate_limiter.check_session_creation_limit(client_ip)
    if not allowed:
        logger.info("Session auto-creation rate limit exceeded", extra={"client_ip": client_ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Session creation limit exceeded. Please try again later.",
            headers={"Retry-After": str(reset_seconds)},
        )

    new_session_id = str(uuid.uuid4())
    session_service = SessionService(db)
    try:
        await session_service.create(new_session_id)
        await rate_limiter.record_session_creation(client_ip)
        logger.info(
            "ChatContext: auto-created session",
            extra={"session_id": new_session_id[:8], "client_ip": client_ip},
        )
        return ChatContext(
            user_id=None,
            session_id=new_session_id,
            is_authenticated=False,
            session_created=True,
            client_ip=client_ip,
        )
    finally:
        await session_service.close()


async def require_session_or_auth(
    context: ChatContext = Depends(get_chat_context),
) -> ChatContext:
    """Require either authentication or a valid session.

    Use this dependency for endpoints that need user/session tracking.

    Raises:
        HTTPException: 401 if neither authenticated nor has session
    """
    if not context.user_id and not context.session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication or session cookie required",
        )
    return context
