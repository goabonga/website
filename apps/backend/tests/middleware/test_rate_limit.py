# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for backend.middleware.rate_limit.RateLimiter."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.middleware.rate_limit import RateLimiter, get_rate_limiter


@pytest.fixture
def mock_pipe():
    """Return a mocked Redis pipeline."""
    pipe = AsyncMock()
    pipe.zremrangebyscore = MagicMock()
    pipe.zcard = MagicMock()
    pipe.zadd = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[0, 0])
    return pipe


@pytest.fixture
def mock_redis(mock_pipe):
    """Return a mocked Redis client with pipeline support."""
    r = AsyncMock()
    r.pipeline = MagicMock(return_value=mock_pipe)
    r.zrem = AsyncMock()
    r.close = AsyncMock()
    return r


@pytest.fixture
def rate_limiter(mock_redis):
    """Return a RateLimiter with mocked Redis."""
    rl = RateLimiter()
    rl._redis = mock_redis
    rl.get_redis = AsyncMock(return_value=mock_redis)
    return rl


class TestCheckRateLimit:
    """Tests for RateLimiter.check_rate_limit."""

    @patch("backend.middleware.rate_limit.settings")
    async def test_authenticated_user_within_limit(self, mock_settings, rate_limiter, mock_pipe):
        """Authenticated user within rate limit is allowed."""
        mock_settings.rate_limit_auth = 60
        mock_settings.rate_limit_window = 60

        # Pipeline returns: [removed_count, current_count]
        # current_count=5, well under limit of 60
        mock_pipe.execute.return_value = [0, 5]

        user_id = uuid.uuid4()
        allowed, remaining, reset_seconds = await rate_limiter.check_rate_limit(
            user_id=user_id, client_ip="192.168.1.1"
        )

        assert allowed is True
        assert remaining == 54  # 60 - 5 - 1
        assert reset_seconds == 60

    @patch("backend.middleware.rate_limit.settings")
    async def test_authenticated_user_over_limit(
        self, mock_settings, rate_limiter, mock_pipe, mock_redis
    ):
        """Authenticated user over rate limit is denied."""
        mock_settings.rate_limit_auth = 60
        mock_settings.rate_limit_window = 60

        # current_count=60, at the limit
        mock_pipe.execute.return_value = [0, 60]

        user_id = uuid.uuid4()
        allowed, remaining, reset_seconds = await rate_limiter.check_rate_limit(
            user_id=user_id, client_ip="192.168.1.1"
        )

        assert allowed is False
        assert remaining == 0
        assert reset_seconds == 60
        # The over-limit request should be removed
        mock_redis.zrem.assert_awaited_once()

    @patch("backend.middleware.rate_limit.settings")
    async def test_anonymous_user_within_limit(self, mock_settings, rate_limiter, mock_pipe):
        """Anonymous user within rate limit is allowed."""
        mock_settings.rate_limit_anon = 10
        mock_settings.rate_limit_window = 60

        # current_count=3, under limit of 10
        mock_pipe.execute.return_value = [0, 3]

        allowed, remaining, reset_seconds = await rate_limiter.check_rate_limit(
            user_id=None, client_ip="10.0.0.1"
        )

        assert allowed is True
        assert remaining == 6  # 10 - 3 - 1
        assert reset_seconds == 60

    @patch("backend.middleware.rate_limit.settings")
    async def test_anonymous_user_over_limit(
        self, mock_settings, rate_limiter, mock_pipe, mock_redis
    ):
        """Anonymous user over rate limit is denied."""
        mock_settings.rate_limit_anon = 10
        mock_settings.rate_limit_window = 60

        # current_count=10, at the limit
        mock_pipe.execute.return_value = [0, 10]

        allowed, remaining, reset_seconds = await rate_limiter.check_rate_limit(
            user_id=None, client_ip="10.0.0.1"
        )

        assert allowed is False
        assert remaining == 0
        assert reset_seconds == 60
        mock_redis.zrem.assert_awaited_once()


class TestCheckSessionCreationLimit:
    """Tests for RateLimiter.check_session_creation_limit."""

    @patch("backend.middleware.rate_limit.settings")
    async def test_within_limit(self, mock_settings, rate_limiter, mock_pipe):
        """Session creation within limit is allowed."""
        mock_settings.session_create_limit = 3
        mock_settings.session_create_window = 86400

        # current_count=1, under limit of 3
        mock_pipe.execute.return_value = [0, 1]

        allowed, remaining, reset_seconds = await rate_limiter.check_session_creation_limit(
            "10.0.0.1"
        )

        assert allowed is True
        assert remaining == 2  # 3 - 1
        assert reset_seconds == 86400

    @patch("backend.middleware.rate_limit.settings")
    async def test_over_limit(self, mock_settings, rate_limiter, mock_pipe):
        """Session creation over limit is denied."""
        mock_settings.session_create_limit = 3
        mock_settings.session_create_window = 86400

        # current_count=3, at the limit
        mock_pipe.execute.return_value = [0, 3]

        allowed, remaining, reset_seconds = await rate_limiter.check_session_creation_limit(
            "10.0.0.1"
        )

        assert allowed is False
        assert remaining == 0
        assert reset_seconds == 86400


class TestRecordSessionCreation:
    """Tests for RateLimiter.record_session_creation."""

    @patch("backend.middleware.rate_limit.settings")
    async def test_record_session_creation_records_in_redis(
        self, mock_settings, rate_limiter, mock_pipe
    ):
        """Recording a session creation adds an entry to the Redis sorted set."""
        mock_settings.session_create_window = 86400

        await rate_limiter.record_session_creation("10.0.0.1")

        # Pipeline should have been used with zadd and expire
        mock_pipe.zadd.assert_called_once()
        mock_pipe.expire.assert_called_once()
        mock_pipe.execute.assert_awaited_once()


class TestGetRedis:
    """Tests for RateLimiter.get_redis."""

    @patch("backend.middleware.rate_limit.redis")
    @patch("backend.middleware.rate_limit.settings")
    async def test_get_redis_creates_connection(self, mock_settings, mock_redis_module):
        """get_redis creates a Redis connection when none exists."""
        mock_settings.rate_limit_redis_url = "redis://localhost:6379/1"
        mock_redis_instance = AsyncMock()
        mock_redis_module.from_url.return_value = mock_redis_instance

        rl = RateLimiter()
        result = await rl.get_redis()

        mock_redis_module.from_url.assert_called_once_with(
            "redis://localhost:6379/1",
            decode_responses=True,
        )
        assert result is mock_redis_instance

    async def test_get_redis_reuses_existing_connection(self):
        """get_redis returns existing connection without creating a new one."""
        existing_redis = AsyncMock()
        rl = RateLimiter()
        rl._redis = existing_redis

        result = await rl.get_redis()

        assert result is existing_redis


class TestClose:
    """Tests for RateLimiter.close."""

    async def test_close_closes_and_resets_redis(self):
        """close() closes the Redis connection and sets _redis to None."""
        mock_redis_instance = AsyncMock()
        rl = RateLimiter()
        rl._redis = mock_redis_instance

        await rl.close()

        mock_redis_instance.close.assert_awaited_once()
        assert rl._redis is None

    async def test_close_when_redis_is_none(self):
        """close() does nothing when _redis is None."""
        rl = RateLimiter()
        assert rl._redis is None

        await rl.close()

        assert rl._redis is None


class TestGetRateLimiter:
    """Tests for the get_rate_limiter module-level function."""

    async def test_get_rate_limiter_returns_instance(self):
        """get_rate_limiter creates and returns a RateLimiter."""
        import backend.middleware.rate_limit as rl_module

        # Reset the global instance
        rl_module._rate_limiter = None

        result = await get_rate_limiter()

        assert isinstance(result, RateLimiter)
        # Clean up
        rl_module._rate_limiter = None

    async def test_get_rate_limiter_returns_same_instance(self):
        """get_rate_limiter returns the same instance on subsequent calls."""
        import backend.middleware.rate_limit as rl_module

        # Reset the global instance
        rl_module._rate_limiter = None

        first = await get_rate_limiter()
        second = await get_rate_limiter()

        assert first is second
        # Clean up
        rl_module._rate_limiter = None
