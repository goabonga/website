# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for main FastAPI application."""

from unittest.mock import MagicMock, patch

import pytest


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        from internal.main import health_check

        result = await health_check()
        assert result.status == "healthy"


class TestGetSwaggerUiOauth2Config:
    def test_returns_config_when_configured(self):
        with patch("internal.main.settings") as s:
            s.oauth2_issuer = "https://auth.example.com"
            s.oauth2_swagger_client_id = "swagger-client"
            from internal.main import get_swagger_ui_oauth2_config

            config = get_swagger_ui_oauth2_config()
            assert "swagger_ui_init_oauth" in config
            assert config["swagger_ui_init_oauth"]["clientId"] == "swagger-client"

    def test_returns_empty_when_no_issuer(self):
        with patch("internal.main.settings") as s:
            s.oauth2_issuer = ""
            s.oauth2_swagger_client_id = "swagger-client"
            from internal.main import get_swagger_ui_oauth2_config

            assert get_swagger_ui_oauth2_config() == {}

    def test_returns_empty_when_no_swagger_client(self):
        with patch("internal.main.settings") as s:
            s.oauth2_issuer = "https://auth.example.com"
            s.oauth2_swagger_client_id = ""
            from internal.main import get_swagger_ui_oauth2_config

            assert get_swagger_ui_oauth2_config() == {}


class TestTokenRefreshMiddleware:
    @pytest.mark.asyncio
    async def test_no_pending_refresh(self):
        from internal.main import TokenRefreshMiddleware

        middleware = TokenRefreshMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_response = MagicMock()

        async def mock_call_next(request):
            return mock_response

        with patch("internal.main.get_pending_token_refresh", return_value=None):
            result = await middleware.dispatch(mock_request, mock_call_next)
            assert result is mock_response

    @pytest.mark.asyncio
    async def test_with_access_token_refresh(self):
        from internal.main import TokenRefreshMiddleware

        middleware = TokenRefreshMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_response = MagicMock()

        async def mock_call_next(request):
            return mock_response

        tokens = {"access_token": "new-at", "expires_in": 7200}
        with (
            patch("internal.main.get_pending_token_refresh", return_value=tokens),
            patch("internal.main.clear_pending_token_refresh") as mock_clear,
            patch("internal.main.settings") as s,
        ):
            s.cookie_secure = False
            result = await middleware.dispatch(mock_request, mock_call_next)
            assert result is mock_response
            mock_response.set_cookie.assert_called()
            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_refresh_token_only(self):
        """Covers branch 54->64: tokens dict has no access_token."""
        from internal.main import TokenRefreshMiddleware

        middleware = TokenRefreshMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_response = MagicMock()

        async def mock_call_next(request):
            return mock_response

        # Tokens dict is truthy but access_token is missing
        tokens = {"refresh_token": "new-rt", "expires_in": 3600}
        with (
            patch("internal.main.get_pending_token_refresh", return_value=tokens),
            patch("internal.main.clear_pending_token_refresh") as mock_clear,
            patch("internal.main.settings") as s,
        ):
            s.cookie_secure = False
            result = await middleware.dispatch(mock_request, mock_call_next)
            assert result is mock_response
            # Only refresh_token cookie set (not access_token)
            mock_response.set_cookie.assert_called_once()
            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_both_tokens(self):
        from internal.main import TokenRefreshMiddleware

        middleware = TokenRefreshMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_response = MagicMock()

        async def mock_call_next(request):
            return mock_response

        tokens = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 3600,
        }
        with (
            patch("internal.main.get_pending_token_refresh", return_value=tokens),
            patch("internal.main.clear_pending_token_refresh"),
            patch("internal.main.settings") as s,
        ):
            s.cookie_secure = False
            result = await middleware.dispatch(mock_request, mock_call_next)
            assert result is mock_response
            assert mock_response.set_cookie.call_count == 2


class TestHealthResponse:
    def test_model(self):
        from internal.main import HealthResponse

        resp = HealthResponse(status="ok")
        assert resp.status == "ok"


class TestAppCreated:
    def test_app_exists(self):
        from internal.main import app

        assert app is not None
        assert app.title is not None
