# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for reachy_mini_api/middleware.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from reachy_mini_api.middleware import RequestLoggingMiddleware


class TestRequestLoggingMiddleware:
    """Tests for RequestLoggingMiddleware."""

    def _make_request(self, method="GET", path="/test", user_id=None, client_id=None):
        """Create a mock request object."""
        request = MagicMock()
        request.method = method
        request.url.path = path
        request.state = MagicMock()
        # Simulate missing attributes that getattr will check
        if user_id:
            request.state.user_id = user_id
        else:
            del request.state.user_id
        if client_id:
            request.state.client_id = client_id
        else:
            del request.state.client_id
        return request

    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        """Process request and log response."""
        middleware = RequestLoggingMiddleware(app=MagicMock())
        request = self._make_request()
        response = MagicMock()
        response.status_code = 200
        call_next = AsyncMock(return_value=response)

        with (
            patch("reachy_mini_api.middleware.set_request_context") as mock_set_ctx,
            patch("reachy_mini_api.middleware.clear_request_context") as mock_clear_ctx,
            patch("reachy_mini_api.middleware.logger") as mock_logger,
        ):
            result = await middleware.dispatch(request, call_next)

        assert result == response
        call_next.assert_awaited_once_with(request)
        mock_set_ctx.assert_called_once()
        mock_clear_ctx.assert_called_once()
        assert mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_dispatch_sets_request_id(self):
        """Set unique request ID on request state."""
        middleware = RequestLoggingMiddleware(app=MagicMock())
        request = self._make_request()
        response = MagicMock()
        response.status_code = 200
        call_next = AsyncMock(return_value=response)

        with (
            patch("reachy_mini_api.middleware.set_request_context"),
            patch("reachy_mini_api.middleware.clear_request_context"),
            patch("reachy_mini_api.middleware.logger"),
        ):
            await middleware.dispatch(request, call_next)

        assert hasattr(request.state, "request_id")

    @pytest.mark.asyncio
    async def test_dispatch_with_user_context(self):
        """Update context when user_id and client_id are set on request."""
        middleware = RequestLoggingMiddleware(app=MagicMock())
        request = self._make_request(user_id="user1", client_id="client1")
        response = MagicMock()
        response.status_code = 200
        call_next = AsyncMock(return_value=response)

        with (
            patch("reachy_mini_api.middleware.set_request_context") as mock_set_ctx,
            patch("reachy_mini_api.middleware.clear_request_context"),
            patch("reachy_mini_api.middleware.logger"),
        ):
            await middleware.dispatch(request, call_next)

        # set_request_context should be called twice: once initially, once with user info
        assert mock_set_ctx.call_count == 2

    @pytest.mark.asyncio
    async def test_dispatch_logs_request_and_response(self):
        """Log incoming request and outgoing response."""
        middleware = RequestLoggingMiddleware(app=MagicMock())
        request = self._make_request(method="POST", path="/api/test")
        response = MagicMock()
        response.status_code = 201
        call_next = AsyncMock(return_value=response)

        with (
            patch("reachy_mini_api.middleware.set_request_context"),
            patch("reachy_mini_api.middleware.clear_request_context"),
            patch("reachy_mini_api.middleware.logger") as mock_logger,
        ):
            await middleware.dispatch(request, call_next)

        # At least 2 info calls: request + response
        assert mock_logger.info.call_count >= 2
        request_log = mock_logger.info.call_args_list[0][0][0]
        assert "REQUEST: POST /api/test" in request_log
        response_log = mock_logger.info.call_args_list[1][0][0]
        assert "RESPONSE: POST /api/test" in response_log
        assert "status=201" in response_log

    @pytest.mark.asyncio
    async def test_dispatch_exception(self):
        """Log error and re-raise on exception."""
        middleware = RequestLoggingMiddleware(app=MagicMock())
        request = self._make_request()
        call_next = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch("reachy_mini_api.middleware.set_request_context"),
            patch("reachy_mini_api.middleware.clear_request_context") as mock_clear,
            patch("reachy_mini_api.middleware.logger") as mock_logger,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await middleware.dispatch(request, call_next)

        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        assert "ERROR:" in error_msg
        assert "RuntimeError" in error_msg
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_clears_context_on_success(self):
        """Clear request context after successful request."""
        middleware = RequestLoggingMiddleware(app=MagicMock())
        request = self._make_request()
        response = MagicMock()
        response.status_code = 200
        call_next = AsyncMock(return_value=response)

        with (
            patch("reachy_mini_api.middleware.set_request_context"),
            patch("reachy_mini_api.middleware.clear_request_context") as mock_clear,
            patch("reachy_mini_api.middleware.logger"),
        ):
            await middleware.dispatch(request, call_next)

        mock_clear.assert_called_once()
