# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the API tracking middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.middleware.api_tracking import APITrackingMiddleware


class TestAPITrackingMiddleware:
    """Tests for APITrackingMiddleware.dispatch covering lines 28-49."""

    def _make_request(self, path: str, tenant_id=None):
        """Helper to create a mock Request with a given path."""
        request = MagicMock()
        request.url.path = path
        state = MagicMock()
        if tenant_id is not None:
            state.tenant_id = tenant_id
        else:
            # Make getattr(request.state, "tenant_id", None) return None
            del state.tenant_id
        request.state = state
        return request

    @pytest.fixture
    def middleware(self):
        app = MagicMock()
        return APITrackingMiddleware(app)

    async def test_non_api_route_passes_through(self, middleware):
        """Non-/v1/ routes are not tracked."""
        request = self._make_request("/docs")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        result = await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)
        assert result == call_next.return_value

    async def test_health_endpoint_v1_skipped(self, middleware):
        """Health check at /v1/health is skipped."""
        request = self._make_request("/v1/health")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        result = await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)
        assert result == call_next.return_value

    async def test_health_endpoint_root_skipped(self, middleware):
        """/health is not a /v1/ path, so it hits the first guard."""
        request = self._make_request("/health")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)

    @patch("knowledge.middleware.api_tracking.async_session_factory")
    async def test_successful_api_call_records_usage(self, mock_session_factory, middleware):
        """2xx response with tenant_id records the API call."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/v1/collections", tenant_id=tenant_id)
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        mock_db = AsyncMock()
        mock_quota_service = MagicMock()
        mock_quota_service.record_api_call = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "knowledge.middleware.api_tracking.QuotaService", return_value=mock_quota_service
        ):
            result = await middleware.dispatch(request, call_next)

        assert result == response
        mock_quota_service.record_api_call.assert_awaited_once_with(tenant_id)
        mock_db.commit.assert_awaited_once()

    @patch("knowledge.middleware.api_tracking.async_session_factory")
    async def test_successful_api_v1_call_records_usage(self, mock_session_factory, middleware):
        """2xx response on /api/v1/* with tenant_id records the API call."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/api/v1/search", tenant_id=tenant_id)
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        mock_db = AsyncMock()
        mock_quota_service = MagicMock()
        mock_quota_service.record_api_call = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "knowledge.middleware.api_tracking.QuotaService", return_value=mock_quota_service
        ):
            result = await middleware.dispatch(request, call_next)

        assert result == response
        mock_quota_service.record_api_call.assert_awaited_once_with(tenant_id)
        mock_db.commit.assert_awaited_once()

    async def test_non_2xx_response_not_tracked(self, middleware):
        """Non-2xx responses are not tracked."""
        request = self._make_request("/v1/collections", tenant_id="some-id")
        response = MagicMock(status_code=404)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result == response

    async def test_no_tenant_id_not_tracked(self, middleware):
        """2xx without tenant_id does not try to record."""
        request = self._make_request("/v1/collections")
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result == response

    @patch("knowledge.middleware.api_tracking.async_session_factory")
    async def test_tracking_exception_does_not_fail_request(self, mock_session_factory, middleware):
        """If tracking fails, the response is still returned."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/v1/collections", tenant_id=tenant_id)
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        mock_session_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("DB connection error")
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await middleware.dispatch(request, call_next)

        assert result == response

    async def test_status_299_is_tracked(self, middleware):
        """Status code 299 (still 2xx) should be tracked."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/v1/data", tenant_id=tenant_id)
        response = MagicMock(status_code=299)
        call_next = AsyncMock(return_value=response)

        with patch("knowledge.middleware.api_tracking.async_session_factory") as mock_sf:
            mock_db = AsyncMock()
            mock_quota_service = MagicMock()
            mock_quota_service.record_api_call = AsyncMock()
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "knowledge.middleware.api_tracking.QuotaService", return_value=mock_quota_service
            ):
                result = await middleware.dispatch(request, call_next)

        assert result == response
        mock_quota_service.record_api_call.assert_awaited_once()

    async def test_status_300_not_tracked(self, middleware):
        """Status code 300 is not 2xx and should not be tracked."""
        request = self._make_request("/v1/data", tenant_id="some-id")
        response = MagicMock(status_code=300)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result == response
