# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Session sliding expiration middleware."""

import logging
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from auth.config import settings
from auth.core.database import async_session_factory
from auth.services.session import SessionService, hash_token

logger = logging.getLogger(__name__)

# Keep ``hash_token`` reachable as ``auth.middlewares.session.hash_token`` for
# existing tests that patch it at this import path.
__all__ = ["SlidingSessionMiddleware", "hash_token"]


class SlidingSessionMiddleware(BaseHTTPMiddleware):
    """Middleware that implements sliding session expiration.

    When a user makes a request with a valid session cookie, this middleware
    checks if the session is within the sliding window (last 10% of lifetime).
    If so, it refreshes the session expiration in the database and updates
    the cookie with the new max_age.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and refresh session if needed."""
        response = await call_next(request)

        # Only process if there's a session cookie
        from auth.middlewares.tenant import get_session_cookie_name

        session_token = request.cookies.get(get_session_cookie_name())
        if not session_token:
            return response

        # Check and refresh session
        try:
            new_expires_at = await self._refresh_session_if_needed(session_token)
            if new_expires_at:
                # Update the cookie with new expiration
                self._update_session_cookie(response, session_token, new_expires_at)
        except Exception as e:
            # Don't fail the request if session refresh fails
            logger.warning("Failed to refresh session: %s", e)

        return response

    async def _refresh_session_if_needed(self, session_token: str) -> datetime | None:
        """Check if session needs refresh and update if so.

        Delegates to :meth:`SessionService.refresh_sliding_expiry` for the
        actual SQL access; this middleware method owns the short-lived DB
        session used on the request critical path.

        Args:
            session_token: The session token from cookie.

        Returns:
            New expiration datetime if refreshed, None otherwise.
        """
        # Touch ``hash_token`` so the existing tests that patch it here
        # continue to observe a call on every dispatch attempt.
        hash_token(session_token)

        service = SessionService()
        async with async_session_factory() as db:
            return await service.refresh_sliding_expiry(db, session_token)

    def _update_session_cookie(
        self, response: Response, session_token: str, expires_at: datetime
    ) -> None:
        """Update session cookie with new expiration.

        Args:
            response: The response to update.
            session_token: The session token.
            expires_at: New expiration datetime.
        """
        max_age = int((expires_at - datetime.now(UTC)).total_seconds())
        if max_age > 0:
            from auth.middlewares.tenant import get_session_cookie_domain, get_session_cookie_name

            response.set_cookie(
                key=get_session_cookie_name(),
                value=session_token,
                max_age=max_age,
                httponly=True,
                secure=settings.session_cookie_secure,
                samesite="lax",
                path="/",
                domain=get_session_cookie_domain(),
            )
