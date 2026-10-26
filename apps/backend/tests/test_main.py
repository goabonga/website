# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.main module."""

from unittest.mock import patch

from backend import __version__
from backend.config import settings
from backend.main import app, get_swagger_ui_oauth2_config
from httpx import ASGITransport, AsyncClient


class TestHealthCheck:
    """Tests for the /health endpoint."""

    async def test_health_check_returns_healthy(self) -> None:
        """GET /health returns 200 with {"status": "healthy"}."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_health_is_hidden_from_schema(self) -> None:
        """The health route is not part of the OpenAPI schema."""
        assert "/health" not in app.openapi()["paths"]


class TestAppConfiguration:
    """Tests for FastAPI app configuration."""

    def test_app_has_correct_title(self) -> None:
        """The app title matches settings.app_name."""
        assert app.title == settings.app_name

    def test_app_version_matches_package(self) -> None:
        """The app version is the package version."""
        assert app.version == __version__

    def test_docs_are_disabled_by_default(self) -> None:
        """Swagger UI, ReDoc and the schema are off unless DOCS_ENABLED is set."""
        assert settings.docs_enabled is False
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None


class TestSwaggerOAuth2Config:
    """Tests for get_swagger_ui_oauth2_config."""

    def test_returns_oauth2_config_when_configured(self) -> None:
        """PKCE settings are returned when issuer and client id are set."""
        with patch("backend.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger-client-id"
            result = get_swagger_ui_oauth2_config()

        assert result["swagger_ui_init_oauth"]["clientId"] == "swagger-client-id"
        assert result["swagger_ui_init_oauth"]["usePkceWithAuthorizationCodeGrant"] is True
        assert result["swagger_ui_parameters"]["persistAuthorization"] is True

    def test_returns_empty_without_client_id(self) -> None:
        """Nothing is returned when the Swagger client id is missing."""
        with patch("backend.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = ""
            assert get_swagger_ui_oauth2_config() == {}

    def test_returns_empty_without_issuer(self) -> None:
        """Nothing is returned when no issuer is configured."""
        with patch("backend.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = "swagger-client-id"
            assert get_swagger_ui_oauth2_config() == {}


class TestChatRouter:
    """Tests for the chat router registration."""

    def test_chat_route_is_registered(self) -> None:
        """POST /api/v1/chat is served by the application."""
        paths = app.openapi()["paths"]
        assert "post" in paths["/api/v1/chat"]

    def test_description_lists_features(self) -> None:
        """The OpenAPI description mentions the chat interface and OAuth2."""
        assert "Chat interface" in app.description
        assert "OAuth2" in app.description
