# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/main.py."""

from unittest.mock import AsyncMock, patch


class TestAppRoutes:
    """Tests for registered app routes."""

    def test_docs_routes_enabled_by_default(self):
        """Docs routes should be registered when docs_enabled is True (default)."""
        from team.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/docs" in routes
        assert "/openapi.json" in routes
        assert "/redoc" in routes

    def test_app_title(self):
        """App title should match settings."""
        from team.main import app

        assert app.title is not None
        assert len(app.title) > 0

    def test_app_version(self):
        """App version should be set."""
        from team.main import app

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
        from team import __version__

        response = await client.get("/health")
        data = response.json()

        assert data["version"] == __version__


class TestLifespan:
    """Tests for app lifespan startup/shutdown."""

    async def test_lifespan_startup_logs(self):
        """Lifespan startup should log a starting message."""
        from team.main import app as main_app
        from team.main import lifespan

        with patch("team.main.logger") as mock_logger:
            async with lifespan(main_app):
                mock_logger.info.assert_called()
                startup_call = mock_logger.info.call_args_list[0]
                assert "Starting" in str(startup_call)

    async def test_lifespan_shutdown_logs(self):
        """Lifespan shutdown should log a shutting down message."""
        from team.main import app as main_app
        from team.main import lifespan

        with (
            patch("team.main.logger") as mock_logger,
            patch("team.main.jwks_manager") as mock_jwks,
            patch("team.main.token_exchange_client") as mock_te,
            patch("team.main.introspection_client") as mock_intro,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_intro.close = AsyncMock()

            async with lifespan(main_app):
                pass

            shutdown_calls = [
                c for c in mock_logger.info.call_args_list if "Shutting down" in str(c)
            ]
            assert len(shutdown_calls) >= 1

    async def test_lifespan_shutdown_closes_jwks_manager(self):
        """Lifespan shutdown should close the JWKS manager."""
        from team.main import app as main_app
        from team.main import lifespan

        with (
            patch("team.main.logger"),
            patch("team.main.jwks_manager") as mock_jwks,
            patch("team.main.token_exchange_client") as mock_te,
            patch("team.main.introspection_client") as mock_intro,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_intro.close = AsyncMock()

            async with lifespan(main_app):
                pass

            mock_jwks.close.assert_awaited_once()

    async def test_lifespan_shutdown_closes_introspection_client(self):
        """Lifespan shutdown should close the introspection client."""
        from team.main import app as main_app
        from team.main import lifespan

        with (
            patch("team.main.logger"),
            patch("team.main.jwks_manager") as mock_jwks,
            patch("team.main.token_exchange_client") as mock_te,
            patch("team.main.introspection_client") as mock_intro,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_intro.close = AsyncMock()

            async with lifespan(main_app):
                pass

            mock_intro.close.assert_awaited_once()

    async def test_lifespan_shutdown_closes_token_exchange_client(self):
        """Lifespan shutdown should close the token exchange client."""
        from team.main import app as main_app
        from team.main import lifespan

        with (
            patch("team.main.logger"),
            patch("team.main.jwks_manager") as mock_jwks,
            patch("team.main.token_exchange_client") as mock_te,
            patch("team.main.introspection_client") as mock_intro,
        ):
            mock_jwks.close = AsyncMock()
            mock_te.close = AsyncMock()
            mock_intro.close = AsyncMock()

            async with lifespan(main_app):
                pass

            mock_te.close.assert_awaited_once()


class TestGetSwaggerOauth2Config:
    """Tests for get_swagger_ui_oauth2_config()."""

    def test_returns_empty_dict_without_issuer(self):
        """Should return empty dict when oauth2_issuer is not set."""
        with patch("team.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = "some-client"

            from team.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()
            assert result == {}

    def test_returns_empty_dict_without_client_id(self):
        """Should return empty dict when oauth2_swagger_client_id is not set."""
        with patch("team.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = ""

            from team.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()
            assert result == {}

    def test_returns_config_with_both_set(self):
        """Should return full config when both issuer and client_id are set."""
        with patch("team.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger-client"

            from team.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()

        assert "swagger_ui_init_oauth" in result
        assert result["swagger_ui_init_oauth"]["clientId"] == "swagger-client"
        assert result["swagger_ui_init_oauth"]["usePkceWithAuthorizationCodeGrant"] is True
        assert "swagger_ui_parameters" in result
        assert result["swagger_ui_parameters"]["persistAuthorization"] is True

    def test_returns_empty_dict_when_both_empty(self):
        """Should return empty dict when both settings are empty."""
        with patch("team.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = ""

            from team.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()
            assert result == {}


class TestPlatformRoutes:
    """Tests for the registration of the platform routes."""

    async def test_platform_team_route_is_registered(self, client):
        """The /platform/team route is served and requires authentication."""
        response = await client.get("/platform/team")
        assert response.status_code == 401
