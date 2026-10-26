# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.middlewares.session — SlidingSessionMiddleware."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_execute_result, make_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COOKIE_NAME = "session_id"
COOKIE_DOMAIN = ".example.com"
SESSION_EXPIRY_DAYS = 7


def _make_middleware():
    """Create a SlidingSessionMiddleware with a mock app."""
    from auth.middlewares.session import SlidingSessionMiddleware

    mock_app = MagicMock()
    return SlidingSessionMiddleware(mock_app)


def _make_request(cookies=None):
    """Create a mock Starlette Request with optional cookies."""
    request = MagicMock()
    request.cookies = cookies or {}
    return request


def _make_call_next(response=None):
    """Create a mock call_next that returns the given response."""
    resp = response or MagicMock()
    return AsyncMock(return_value=resp), resp


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    """Tests for the dispatch method."""

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value=COOKIE_NAME)
    async def test_no_session_cookie_returns_response_unchanged(self, mock_cookie_name):
        """dispatch -- no session cookie returns response unchanged."""
        middleware = _make_middleware()
        request = _make_request(cookies={})
        call_next, response = _make_call_next()

        result = await middleware.dispatch(request, call_next)

        assert result is response
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value=COOKIE_NAME)
    async def test_session_cookie_refresh_returns_none_no_cookie_update(self, mock_cookie_name):
        """dispatch -- session cookie present, refresh returns None, no cookie update."""
        middleware = _make_middleware()
        request = _make_request(cookies={COOKIE_NAME: "some_token"})
        call_next, response = _make_call_next()

        with (
            patch.object(
                middleware, "_refresh_session_if_needed", new_callable=AsyncMock, return_value=None
            ) as mock_refresh,
            patch.object(middleware, "_update_session_cookie") as mock_update,
        ):
            result = await middleware.dispatch(request, call_next)

        assert result is response
        mock_refresh.assert_awaited_once_with("some_token")
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value=COOKIE_NAME)
    async def test_session_cookie_refresh_returns_datetime_cookie_updated(self, mock_cookie_name):
        """dispatch -- session cookie present, refresh returns new datetime, cookie updated."""
        middleware = _make_middleware()
        request = _make_request(cookies={COOKIE_NAME: "some_token"})
        call_next, response = _make_call_next()
        new_expires = datetime.now(UTC) + timedelta(days=7)

        with (
            patch.object(
                middleware,
                "_refresh_session_if_needed",
                new_callable=AsyncMock,
                return_value=new_expires,
            ) as mock_refresh,
            patch.object(middleware, "_update_session_cookie") as mock_update,
        ):
            result = await middleware.dispatch(request, call_next)

        assert result is response
        mock_refresh.assert_awaited_once_with("some_token")
        mock_update.assert_called_once_with(response, "some_token", new_expires)

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value=COOKIE_NAME)
    async def test_refresh_raises_exception_response_still_returned(self, mock_cookie_name):
        """dispatch -- refresh raises exception, response still returned, warning logged."""
        middleware = _make_middleware()
        request = _make_request(cookies={COOKIE_NAME: "some_token"})
        call_next, response = _make_call_next()

        with (
            patch.object(
                middleware,
                "_refresh_session_if_needed",
                new_callable=AsyncMock,
                side_effect=RuntimeError("db down"),
            ),
            patch("auth.middlewares.session.logger") as mock_logger,
        ):
            result = await middleware.dispatch(request, call_next)

        assert result is response
        mock_logger.warning.assert_called_once()
        assert "db down" in str(mock_logger.warning.call_args)


# ---------------------------------------------------------------------------
# _refresh_session_if_needed
# ---------------------------------------------------------------------------


class TestRefreshSessionIfNeeded:
    """Tests for the _refresh_session_if_needed method."""

    @pytest.mark.asyncio
    @patch("auth.middlewares.session.settings")
    @patch("auth.middlewares.session.hash_token", return_value="hashed_token")
    @patch("auth.middlewares.session.async_session_factory")
    async def test_no_session_found_returns_none(
        self, mock_factory, mock_hash_token, mock_settings
    ):
        """_refresh_session_if_needed -- no session found returns None."""
        mock_settings.session_expiry_days = SESSION_EXPIRY_DAYS

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        # async_session_factory() used as async context manager
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        middleware = _make_middleware()
        result = await middleware._refresh_session_if_needed("raw_token")

        assert result is None
        mock_hash_token.assert_called_once_with("raw_token")
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("auth.middlewares.session.settings")
    @patch("auth.middlewares.session.hash_token", return_value="hashed_token")
    @patch("auth.middlewares.session.async_session_factory")
    async def test_session_not_in_sliding_window_returns_none(
        self, mock_factory, mock_hash_token, mock_settings
    ):
        """_refresh_session_if_needed -- session found but NOT in sliding window returns None."""
        mock_settings.session_expiry_days = SESSION_EXPIRY_DAYS

        # Session expires in 5 days -- well outside the 10% sliding window (0.7 days)
        session_obj = make_session(
            expires_at=datetime.now(UTC) + timedelta(days=5),
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=make_execute_result(scalar_value=session_obj))

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        middleware = _make_middleware()
        result = await middleware._refresh_session_if_needed("raw_token")

        assert result is None
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("auth.middlewares.session.settings")
    @patch("auth.middlewares.session.hash_token", return_value="hashed_token")
    @patch("auth.middlewares.session.async_session_factory")
    async def test_session_in_sliding_window_refreshed(
        self, mock_factory, mock_hash_token, mock_settings
    ):
        """_refresh_session_if_needed -- session in sliding window, refreshed, returns new datetime."""
        mock_settings.session_expiry_days = SESSION_EXPIRY_DAYS

        # Session expires in 0.3 days -- inside the 10% threshold (0.7 days)
        session_obj = make_session(
            expires_at=datetime.now(UTC) + timedelta(hours=7),
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=make_execute_result(scalar_value=session_obj))

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        middleware = _make_middleware()
        result = await middleware._refresh_session_if_needed("raw_token")

        assert result is not None
        assert isinstance(result, datetime)
        # The new expiry should be roughly "now + SESSION_EXPIRY_DAYS"
        expected_min = (
            datetime.now(UTC) + timedelta(days=SESSION_EXPIRY_DAYS) - timedelta(seconds=5)
        )
        expected_max = (
            datetime.now(UTC) + timedelta(days=SESSION_EXPIRY_DAYS) + timedelta(seconds=5)
        )
        assert expected_min <= result <= expected_max
        # The session model should have been updated
        assert session_obj.expires_at == result
        mock_db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# _update_session_cookie
# ---------------------------------------------------------------------------


class TestUpdateSessionCookie:
    """Tests for the _update_session_cookie method."""

    @patch("auth.middlewares.tenant.get_session_cookie_domain", return_value=COOKIE_DOMAIN)
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value=COOKIE_NAME)
    @patch("auth.middlewares.session.settings")
    def test_max_age_positive_sets_cookie(
        self, mock_settings, mock_cookie_name, mock_cookie_domain
    ):
        """_update_session_cookie -- max_age > 0 sets cookie on response."""
        mock_settings.session_cookie_secure = True

        middleware = _make_middleware()
        response = MagicMock()
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        middleware._update_session_cookie(response, "the_token", expires_at)

        response.set_cookie.assert_called_once()
        call_kwargs = response.set_cookie.call_args
        assert call_kwargs.kwargs["key"] == COOKIE_NAME
        assert call_kwargs.kwargs["value"] == "the_token"
        assert call_kwargs.kwargs["max_age"] > 0
        assert call_kwargs.kwargs["httponly"] is True
        assert call_kwargs.kwargs["secure"] is True
        assert call_kwargs.kwargs["samesite"] == "lax"
        assert call_kwargs.kwargs["path"] == "/"
        assert call_kwargs.kwargs["domain"] == COOKIE_DOMAIN

    @patch("auth.middlewares.session.settings")
    def test_max_age_zero_or_negative_does_not_set_cookie(self, mock_settings):
        """_update_session_cookie -- max_age <= 0 does not set cookie."""
        mock_settings.session_cookie_secure = True

        middleware = _make_middleware()
        response = MagicMock()
        # Already expired
        expires_at = datetime.now(UTC) - timedelta(seconds=10)

        middleware._update_session_cookie(response, "the_token", expires_at)

        response.set_cookie.assert_not_called()
