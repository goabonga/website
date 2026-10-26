# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/main.py."""

from unittest.mock import AsyncMock, patch


class TestAppRoutes:
    """Tests for registered app routes."""

    def test_health_route_is_registered(self):
        """The /health route should be registered."""
        from billing.main import app
        from fastapi.testclient import TestClient

        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_docs_routes_disabled_by_default(self):
        """Docs routes should not be registered when docs_enabled is False."""
        from billing.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        for path in ("/docs", "/openapi.json", "/redoc"):
            assert client.get(path).status_code == 404

    def test_app_title(self):
        """App title should match settings."""
        from billing.main import app

        assert app.title is not None
        assert len(app.title) > 0

    def test_app_version(self):
        """App version should be set."""
        from billing.main import app

        assert app.version is not None
        assert len(app.version) > 0


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    async def test_health_returns_200(self, client):
        """Health endpoint should return 200 OK."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_response_body(self, client):
        """Health endpoint should return status and version."""
        response = await client.get("/health")
        data = response.json()

        assert data["status"] == "healthy"
        assert "version" in data
        assert len(data["version"]) > 0

    async def test_health_version_matches_app(self, client):
        """Health endpoint version should match app __version__."""
        from billing import __version__

        response = await client.get("/health")
        data = response.json()

        assert data["version"] == __version__


class TestLifespan:
    """Tests for app lifespan startup/shutdown."""

    async def test_lifespan_startup_logs(self):
        """Lifespan startup should log a starting message."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with patch("billing.main.logger") as mock_logger:
            async with lifespan(main_app):
                mock_logger.info.assert_called()
                startup_call = mock_logger.info.call_args_list[0]
                assert "Starting" in str(startup_call)

    async def test_lifespan_shutdown_logs(self):
        """Lifespan shutdown should log a shutting down message."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with (
            patch("billing.main.logger") as mock_logger,
            patch("billing.main.jwks_manager") as mock_jwks,
            patch("billing.main.token_exchange_client") as mock_te,
            patch("billing.main.introspection_client") as mock_introspection,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_introspection.close = AsyncMock()

            async with lifespan(main_app):
                pass

            # After exiting, shutdown message should be logged
            shutdown_calls = [
                c for c in mock_logger.info.call_args_list if "Shutting down" in str(c)
            ]
            assert len(shutdown_calls) >= 1

    async def test_lifespan_shutdown_closes_jwks_manager(self):
        """Lifespan shutdown should close the JWKS manager."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with (
            patch("billing.main.logger"),
            patch("billing.main.jwks_manager") as mock_jwks,
            patch("billing.main.token_exchange_client") as mock_te,
            patch("billing.main.introspection_client") as mock_introspection,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_introspection.close = AsyncMock()

            async with lifespan(main_app):
                pass

            mock_jwks.close.assert_awaited_once()

    async def test_lifespan_shutdown_closes_token_exchange(self):
        """Lifespan shutdown should close the token exchange client."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with (
            patch("billing.main.logger"),
            patch("billing.main.jwks_manager") as mock_jwks,
            patch("billing.main.token_exchange_client") as mock_te,
            patch("billing.main.introspection_client") as mock_introspection,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_introspection.close = AsyncMock()

            async with lifespan(main_app):
                pass

            mock_te.close.assert_awaited_once()

    async def test_lifespan_shutdown_closes_introspection_client(self):
        """Lifespan shutdown should close the introspection client."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with (
            patch("billing.main.logger"),
            patch("billing.main.jwks_manager") as mock_jwks,
            patch("billing.main.token_exchange_client") as mock_te,
            patch("billing.main.introspection_client") as mock_introspection,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_introspection.close = AsyncMock()

            async with lifespan(main_app):
                pass

            mock_introspection.close.assert_awaited_once()

    async def test_lifespan_shutdown_handles_jwks_close_error(self):
        """Lifespan shutdown should handle errors when closing JWKS manager."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with (
            patch("billing.main.logger"),
            patch("billing.main.jwks_manager") as mock_jwks,
            patch("billing.main.token_exchange_client") as mock_te,
            patch("billing.main.introspection_client") as mock_introspection,
        ):
            mock_jwks.close = AsyncMock(side_effect=Exception("JWKS cleanup error"))
            mock_te.close = AsyncMock()
            mock_introspection.close = AsyncMock()

            # Should not raise
            async with lifespan(main_app):
                pass

    async def test_lifespan_shutdown_handles_te_close_error(self):
        """Lifespan shutdown should handle errors when closing token exchange client."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with (
            patch("billing.main.logger"),
            patch("billing.main.jwks_manager") as mock_jwks,
            patch("billing.main.token_exchange_client") as mock_te,
            patch("billing.main.introspection_client") as mock_introspection,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock(side_effect=Exception("TE cleanup error"))
            mock_introspection.close = AsyncMock()

            # Should not raise
            async with lifespan(main_app):
                pass

    async def test_lifespan_shutdown_handles_introspection_close_error(self):
        """Lifespan shutdown should handle errors when closing introspection client."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with (
            patch("billing.main.logger"),
            patch("billing.main.jwks_manager") as mock_jwks,
            patch("billing.main.token_exchange_client") as mock_te,
            patch("billing.main.introspection_client") as mock_introspection,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_introspection.close = AsyncMock(
                side_effect=Exception("Introspection cleanup error")
            )

            # Should not raise
            async with lifespan(main_app):
                pass


class TestGetSwaggerOauth2Config:
    """Tests for get_swagger_oauth2_config()."""

    def test_returns_empty_dict_without_issuer(self):
        """Should return empty dict when oauth2_issuer is not set."""
        with patch("billing.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = "some-client"

            from billing.main import get_swagger_oauth2_config

            result = get_swagger_oauth2_config()
            assert result == {}

    def test_returns_empty_dict_without_client_id(self):
        """Should return empty dict when oauth2_swagger_client_id is not set."""
        with patch("billing.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = ""

            from billing.main import get_swagger_oauth2_config

            result = get_swagger_oauth2_config()
            assert result == {}

    def test_returns_config_with_both_set(self):
        """Should return full config when both issuer and client_id are set."""
        with patch("billing.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger-client"

            from billing.main import get_swagger_oauth2_config

            result = get_swagger_oauth2_config()

        assert "swagger_ui_init_oauth" in result
        assert result["swagger_ui_init_oauth"]["clientId"] == "swagger-client"
        assert result["swagger_ui_init_oauth"]["usePkceWithAuthorizationCodeGrant"] is True
        assert "swagger_ui_parameters" in result
        assert result["swagger_ui_parameters"]["persistAuthorization"] is True

    def test_returns_empty_dict_when_both_empty(self):
        """Should return empty dict when both settings are empty."""
        with patch("billing.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = ""

            from billing.main import get_swagger_oauth2_config

            result = get_swagger_oauth2_config()
            assert result == {}
