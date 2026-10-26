# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.main module."""

from unittest.mock import AsyncMock, patch


class TestAppConfiguration:
    """Tests for FastAPI app configuration."""

    def test_app_title(self):
        from analytics.main import app

        assert app.title == "Analytics"

    def test_docs_disabled_when_docs_enabled_false(self):
        from analytics.main import app

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    def test_cors_middleware_installed(self):
        from analytics.main import app
        from fastapi.middleware.cors import CORSMiddleware

        assert any(m.cls is CORSMiddleware for m in app.user_middleware)

    def test_routes_registered(self):
        from analytics.main import app

        assert app.url_path_for("health_check") == "/health"
        assert app.url_path_for("security_txt") == "/.well-known/security.txt"
        assert app.url_path_for("collect_events") == "/collect"
        assert app.url_path_for("collect_beacon") == "/collect"
        assert app.url_path_for("track_pixel", pixel_key="k") == "/p/k.gif"
        assert app.url_path_for("track_pixel_no_extension", pixel_key="k") == "/p/k"
        assert app.url_path_for("track_link", tracking_key="k") == "/t/k"


class TestVersion:
    """Tests for package version."""

    def test_version_is_set(self):
        from analytics import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_format(self):
        from analytics import __version__

        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)


class TestSwaggerConfig:
    """Tests for get_swagger_oauth2_config."""

    def test_returns_empty_when_no_issuer(self):
        from analytics.main import get_swagger_oauth2_config

        with patch("analytics.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            mock_settings.oauth2_swagger_client_id = "client"
            result = get_swagger_oauth2_config()
        assert result == {}

    def test_returns_empty_when_no_client_id(self):
        from analytics.main import get_swagger_oauth2_config

        with patch("analytics.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = ""
            result = get_swagger_oauth2_config()
        assert result == {}

    def test_returns_config_when_both_set(self):
        from analytics.main import get_swagger_oauth2_config

        with patch("analytics.main.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger-client"
            result = get_swagger_oauth2_config()
        assert "swagger_ui_init_oauth" in result
        assert result["swagger_ui_init_oauth"]["clientId"] == "swagger-client"


class TestLifespan:
    """Tests for lifespan context manager."""

    async def test_lifespan_closes_resources_on_shutdown(self):
        from analytics.main import lifespan

        mock_app = AsyncMock()

        with (
            patch("analytics.auth.jwt.jwt_validator") as mock_jwt,
            patch("analytics.auth.token_exchange.token_exchange_client") as mock_tex,
        ):
            mock_jwt.close = AsyncMock()
            mock_tex.close = AsyncMock()
            async with lifespan(mock_app):
                pass
            mock_jwt.close.assert_called_once()
            mock_tex.close.assert_called_once()
