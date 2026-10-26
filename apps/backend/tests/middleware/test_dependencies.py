# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for backend.middleware.dependencies."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.middleware.dependencies import check_rate_limit, check_rate_limit_with_context
from backend.middleware.rate_limit import RateLimiter
from backend.session.dependencies import ChatContext
from fastapi import HTTPException


@pytest.fixture
def mock_request():
    """Return a mocked FastAPI Request with headers and client."""
    request = MagicMock()
    request.headers = {"X-Forwarded-For": "203.0.113.50"}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.state = MagicMock()
    return request


@pytest.fixture
def mock_user():
    """Return a mocked authenticated User."""
    from backend.auth.models import User

    return User(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        email="test@example.com",
        name="Test User",
        scopes=["openid", "profile"],
    )


@pytest.fixture
def mock_rate_limiter():
    """Return a mocked RateLimiter."""
    rl = AsyncMock(spec=RateLimiter)
    rl.check_rate_limit = AsyncMock(return_value=(True, 59, 60))
    return rl


@pytest.fixture
def mock_context():
    """Return a mocked ChatContext."""
    return ChatContext(
        user_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        session_id=None,
        is_authenticated=True,
        client_ip="203.0.113.50",
    )


class TestCheckRateLimit:
    """Tests for check_rate_limit dependency."""

    async def test_allowed_returns_user(self, mock_request, mock_user, mock_rate_limiter):
        """When rate limit is not exceeded, the user is returned."""
        mock_rate_limiter.check_rate_limit.return_value = (True, 59, 60)

        result = await check_rate_limit(
            request=mock_request,
            user=mock_user,
            rate_limiter=mock_rate_limiter,
        )

        assert result == mock_user
        mock_rate_limiter.check_rate_limit.assert_awaited_once_with(
            user_id=mock_user.id,
            client_ip="203.0.113.50",
        )
        assert mock_request.state.rate_limit_remaining == 59
        assert mock_request.state.rate_limit_reset == 60

    async def test_denied_raises_429(self, mock_request, mock_user, mock_rate_limiter):
        """When rate limit is exceeded, a 429 HTTPException is raised."""
        mock_rate_limiter.check_rate_limit.return_value = (False, 0, 60)

        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(
                request=mock_request,
                user=mock_user,
                rate_limiter=mock_rate_limiter,
            )

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail
        assert exc_info.value.headers["Retry-After"] == "60"

    async def test_anonymous_user_allowed(self, mock_request, mock_rate_limiter):
        """When user is None and rate limit allows, None is returned."""
        mock_rate_limiter.check_rate_limit.return_value = (True, 9, 60)

        result = await check_rate_limit(
            request=mock_request,
            user=None,
            rate_limiter=mock_rate_limiter,
        )

        assert result is None
        mock_rate_limiter.check_rate_limit.assert_awaited_once_with(
            user_id=None,
            client_ip="203.0.113.50",
        )


class TestCheckRateLimitWithContext:
    """Tests for check_rate_limit_with_context dependency."""

    async def test_allowed_returns_context(self, mock_request, mock_context, mock_rate_limiter):
        """When rate limit is not exceeded, the context is returned."""
        mock_rate_limiter.check_rate_limit.return_value = (True, 59, 60)

        result = await check_rate_limit_with_context(
            request=mock_request,
            context=mock_context,
            rate_limiter=mock_rate_limiter,
        )

        assert result == mock_context
        mock_rate_limiter.check_rate_limit.assert_awaited_once_with(
            user_id=mock_context.user_id,
            client_ip="203.0.113.50",
        )
        assert mock_request.state.rate_limit_remaining == 59
        assert mock_request.state.rate_limit_reset == 60

    async def test_denied_raises_429(self, mock_request, mock_context, mock_rate_limiter):
        """When rate limit is exceeded, a 429 HTTPException is raised."""
        mock_rate_limiter.check_rate_limit.return_value = (False, 0, 60)

        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit_with_context(
                request=mock_request,
                context=mock_context,
                rate_limiter=mock_rate_limiter,
            )

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail
        assert exc_info.value.headers["Retry-After"] == "60"
        assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"
