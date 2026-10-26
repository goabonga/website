# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.main module."""

from unittest.mock import AsyncMock, patch

import pytest
from mailler import __version__
from mailler.main import app, lifespan


class TestApplication:
    """Application factory configuration."""

    def test_metadata(self):
        assert app.title == "Mailler API"
        assert app.version == __version__

    def test_docs_disabled_by_default(self):
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    def test_health_route_registered(self):
        assert app.url_path_for("health_check") == "/health"


class TestLifespan:
    """Application lifespan handler."""

    async def test_lifespan_runs_startup_and_shutdown(self):
        async with lifespan(app):
            pass


class TestCors:
    """CORS middleware."""

    async def test_preflight_allowed_origin(self, client):
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://frontend.example"

    async def test_preflight_unknown_origin_not_allowed(self, client):
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in response.headers


class TestSwaggerConfig:
    """Tests for get_swagger_ui_oauth2_config ."""

    def test_swagger_config_when_fully_configured(self):
        """Cover line 55: returns OAuth2 config when issuer and client ID are set."""
        with patch("mailler.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "test-client-id"
            from mailler.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()

        assert "swagger_ui_init_oauth" in result
        assert result["swagger_ui_init_oauth"]["clientId"] == "test-client-id"
        assert result["swagger_ui_init_oauth"]["usePkceWithAuthorizationCodeGrant"] is True
        assert "swagger_ui_parameters" in result
        assert result["swagger_ui_parameters"]["persistAuthorization"] is True

    def test_swagger_config_when_no_issuer(self):
        """Returns empty dict when oauth2_issuer is not set."""
        with patch("mailler.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = None
            mock_settings.oauth2_swagger_client_id = "test-client-id"
            from mailler.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()

        assert result == {}

    def test_swagger_config_when_no_client_id(self):
        """Returns empty dict when oauth2_swagger_client_id is not set."""
        with patch("mailler.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = None
            from mailler.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()

        assert result == {}

    def test_swagger_config_when_both_empty(self):
        """Returns empty dict when both settings are falsy."""
        with patch("mailler.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = ""
            from mailler.main import get_swagger_ui_oauth2_config

            result = get_swagger_ui_oauth2_config()

        assert result == {}


class TestLifespanAuthCleanup:
    """Tests for application lifespan handler ."""

    @pytest.mark.asyncio
    async def test_lifespan_cleanup(self):
        """Cover lines 34-42: lifespan startup and shutdown cleanup."""
        mock_jwks = AsyncMock()
        mock_introspection = AsyncMock()
        mock_te = AsyncMock()

        with (
            patch("mailler.auth.jwks_manager", mock_jwks),
            patch("mailler.auth.introspection_client", mock_introspection),
            patch("mailler.auth.token_exchange_client", mock_te),
        ):
            from mailler.main import app, lifespan

            async with lifespan(app):
                pass  # Startup phase

            # Verify cleanup was called on shutdown
            mock_jwks.close.assert_awaited_once()
            mock_introspection.close.assert_awaited_once()
            mock_te.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_cleanup_handles_close_errors(self):
        """Cover lines 41-42, 45-46, 49-50: exception handlers when close() fails."""
        mock_jwks = AsyncMock()
        mock_jwks.close.side_effect = Exception("jwks error")
        mock_introspection = AsyncMock()
        mock_introspection.close.side_effect = Exception("introspection error")
        mock_te = AsyncMock()
        mock_te.close.side_effect = Exception("te error")

        with (
            patch("mailler.auth.jwks_manager", mock_jwks),
            patch("mailler.auth.introspection_client", mock_introspection),
            patch("mailler.auth.token_exchange_client", mock_te),
        ):
            from mailler.main import app, lifespan

            async with lifespan(app):
                pass

            # All close() were attempted despite errors
            mock_jwks.close.assert_awaited_once()
            mock_te.close.assert_awaited_once()
            mock_introspection.close.assert_awaited_once()
