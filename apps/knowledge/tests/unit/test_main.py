# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for the application wiring in knowledge/main.py and internal.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient


class TestLifespanLogging:
    """Test the lifespan context manager."""

    async def test_lifespan_logs_startup_and_shutdown(self):
        with (
            patch("knowledge.main.logger") as mock_logger,
            patch("knowledge.main.settings") as mock_settings,
        ):
            mock_settings.app_name = "Test App"
            from knowledge.main import lifespan

            async with lifespan(MagicMock()):
                assert mock_logger.info.call_count == 1
            assert mock_logger.info.call_count == 2


class TestApplicationWiring:
    """Test that the public and internal applications are exposed."""

    async def test_public_docs_disabled_by_default(self, client: AsyncClient):
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 404

    async def test_internal_docs_are_served(self, client: AsyncClient):
        response = await client.get("/internal/docs")
        assert response.status_code == 200
        response = await client.get("/internal/openapi.json")
        assert response.status_code == 200
        assert "/health" not in response.json()["paths"]

    async def test_health_is_served_by_internal_app(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    async def test_cors_headers_on_preflight(self, client: AsyncClient):
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


class TestLifespanCleanup:
    """Test that the lifespan closes the auth clients on shutdown."""

    async def test_lifespan_startup_and_shutdown(self):
        """Lifespan logs startup, yields, then cleans up."""
        mock_jwt = AsyncMock()
        mock_token_exchange = AsyncMock()

        with (
            patch("knowledge.main.get_jwt_validator", return_value=mock_jwt),
            patch("knowledge.main.get_token_exchange_client", return_value=mock_token_exchange),
            patch("knowledge.main.logger") as mock_logger,
            patch("knowledge.main.settings") as mock_settings,
        ):
            mock_settings.app_name = "Test App"
            from knowledge.main import lifespan

            mock_app = MagicMock()
            async with lifespan(mock_app):
                # During startup, info should have been logged
                assert mock_logger.info.called

            # After shutdown, close should be called
            mock_jwt.close.assert_awaited_once()
            mock_token_exchange.close.assert_awaited_once()

    async def test_lifespan_shutdown_handles_jwt_exception(self):
        """Lifespan handles exceptions during JWT validator cleanup."""
        mock_jwt = AsyncMock()
        mock_jwt.close.side_effect = RuntimeError("jwt close error")
        mock_token_exchange = AsyncMock()

        with (
            patch("knowledge.main.get_jwt_validator", return_value=mock_jwt),
            patch("knowledge.main.get_token_exchange_client", return_value=mock_token_exchange),
            patch("knowledge.main.logger"),
            patch("knowledge.main.settings") as mock_settings,
        ):
            mock_settings.app_name = "Test App"
            from knowledge.main import lifespan

            mock_app = MagicMock()
            # Should not raise
            async with lifespan(mock_app):
                pass

            mock_jwt.close.assert_awaited_once()
            mock_token_exchange.close.assert_awaited_once()

    async def test_lifespan_shutdown_handles_token_exchange_exception(self):
        """Lifespan handles exceptions during token exchange cleanup."""
        mock_jwt = AsyncMock()
        mock_token_exchange = AsyncMock()
        mock_token_exchange.close.side_effect = RuntimeError("token close error")

        with (
            patch("knowledge.main.get_jwt_validator", return_value=mock_jwt),
            patch("knowledge.main.get_token_exchange_client", return_value=mock_token_exchange),
            patch("knowledge.main.logger"),
            patch("knowledge.main.settings") as mock_settings,
        ):
            mock_settings.app_name = "Test App"
            from knowledge.main import lifespan

            mock_app = MagicMock()
            # Should not raise
            async with lifespan(mock_app):
                pass

            mock_token_exchange.close.assert_awaited_once()


class TestGetSwaggerOAuth2Config:
    """Test get_swagger_oauth2_config (lines 55-68, especially line 60)."""

    def test_returns_empty_when_no_issuer(self):
        with patch("knowledge.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = "some-client"
            from knowledge.main import get_swagger_oauth2_config

            result = get_swagger_oauth2_config()
            assert result == {}

    def test_returns_empty_when_no_client_id(self):
        with patch("knowledge.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = ""
            from knowledge.main import get_swagger_oauth2_config

            result = get_swagger_oauth2_config()
            assert result == {}

    def test_returns_config_when_both_set(self):
        with patch("knowledge.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "my-client-id"
            from knowledge.main import get_swagger_oauth2_config

            result = get_swagger_oauth2_config()
            assert "swagger_ui_init_oauth" in result
            assert result["swagger_ui_init_oauth"]["clientId"] == "my-client-id"
            assert result["swagger_ui_init_oauth"]["usePkceWithAuthorizationCodeGrant"] is True
            assert "swagger_ui_parameters" in result
            assert result["swagger_ui_parameters"]["persistAuthorization"] is True
