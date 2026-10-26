# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the application object and the health endpoint."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from reachy_mini_api import __version__
from reachy_mini_api.main import (
    HealthResponse,
    app,
    get_swagger_ui_oauth2_config,
    health_check,
    lifespan,
)

client = TestClient(app)


class TestApplication:
    """Tests for the FastAPI application."""

    def test_title_and_version(self):
        """The application exposes the configured name and the package version."""
        assert app.title == "Reachy Mini API"
        assert app.version == __version__

    def test_version_format(self):
        """The package version is a semantic version."""
        assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)

    def test_documentation_disabled_by_default(self):
        """Swagger, ReDoc and the OpenAPI schema are not served by default."""
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404

    def test_unknown_path_returns_404(self):
        """Unknown paths answer 404."""
        assert client.get("/nope").status_code == 404

    def test_cors_headers(self):
        """CORS headers are added for cross-origin requests."""
        response = client.get("/health", headers={"Origin": "https://example.com"})
        assert response.headers["access-control-allow-origin"] in ("*", "https://example.com")


class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_handler(self):
        """The handler returns a healthy response."""
        result = await health_check()
        assert result.status == "healthy"

    def test_http_response(self):
        """The endpoint answers 200 with the healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_hidden_from_schema(self):
        """The endpoint is excluded from the OpenAPI schema."""
        paths = app.openapi()["paths"]
        assert "/health" not in paths


class TestHealthResponse:
    """Tests for the HealthResponse model."""

    def test_create(self):
        """Create a HealthResponse."""
        assert HealthResponse(status="healthy").status == "healthy"


class TestLifespan:
    """Tests for the lifespan context manager."""

    async def test_startup_and_shutdown(self):
        """Configure logging on startup and log both transitions."""
        with (
            patch("reachy_mini_api.main.setup_logging") as mock_setup,
            patch("reachy_mini_api.main.logger") as mock_logger,
            patch("reachy_mini_api.main.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.main.introspection_client") as mock_intro,
            patch("reachy_mini_api.main.token_exchange_client") as mock_tex,
        ):
            mock_jwks.close = AsyncMock()
            mock_intro.close = AsyncMock()
            mock_tex.close = AsyncMock()
            async with lifespan(MagicMock()):
                mock_setup.assert_called_once_with(level="INFO")
                assert mock_logger.info.call_count == 1
                mock_jwks.close.assert_not_awaited()
            assert mock_logger.info.call_count == 2
            mock_jwks.close.assert_awaited_once()
            mock_intro.close.assert_awaited_once()
            mock_tex.close.assert_awaited_once()

    def test_request_logging_middleware_registered(self):
        """The request logging middleware wraps the application."""
        names = [m.cls.__name__ for m in app.user_middleware]
        assert "RequestLoggingMiddleware" in names


class TestGetSwaggerUiOauth2Config:
    """Tests for get_swagger_ui_oauth2_config."""

    @patch("reachy_mini_api.main.settings")
    def test_returns_empty_when_no_issuer(self, mock_settings):
        """Return an empty dict when the OAuth2 issuer is not set."""
        mock_settings.oauth2_issuer = ""
        mock_settings.oauth2_swagger_client_id = "some-id"
        assert get_swagger_ui_oauth2_config() == {}

    @patch("reachy_mini_api.main.settings")
    def test_returns_empty_when_no_client_id(self, mock_settings):
        """Return an empty dict when the Swagger client ID is not set."""
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_swagger_client_id = ""
        assert get_swagger_ui_oauth2_config() == {}

    @patch("reachy_mini_api.main.settings")
    def test_returns_config_when_fully_set(self, mock_settings):
        """Return the PKCE configuration when issuer and client ID are set."""
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_swagger_client_id = "swagger-client"
        result = get_swagger_ui_oauth2_config()
        assert result["swagger_ui_init_oauth"]["clientId"] == "swagger-client"
        assert result["swagger_ui_init_oauth"]["usePkceWithAuthorizationCodeGrant"] is True
        assert result["swagger_ui_parameters"]["persistAuthorization"] is True
