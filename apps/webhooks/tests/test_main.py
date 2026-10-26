# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for webhooks.main module."""

import importlib
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient


class TestAppConfiguration:
    """Tests for FastAPI app configuration."""

    def test_app_title(self):
        from webhooks.main import app

        assert app.title == "Webhooks"

    def test_docs_disabled_when_docs_enabled_false(self):
        from webhooks.main import app

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    async def test_health_over_http(self):
        from webhooks.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    async def test_unknown_path_returns_404(self):
        from webhooks.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/unknown")
        assert response.status_code == 404

    async def test_docs_endpoint_returns_404(self):
        from webhooks.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/docs")
        assert response.status_code == 404


class TestVersion:
    """Tests for package version."""

    def test_version_is_set(self):
        from webhooks import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_format(self):
        from webhooks import __version__

        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)


class TestConfigurableApp:
    """Tests for settings-driven behaviour of the app module."""

    def test_docs_enabled_exposes_documentation_urls(self):
        import webhooks.main as main_module
        from webhooks.config import Settings

        with patch.dict("os.environ", {"DOCS_ENABLED": "true"}, clear=True):
            enabled = Settings(_env_file=None)
        try:
            with patch("webhooks.config.settings", enabled):
                importlib.reload(main_module)
                assert main_module.app.docs_url == "/docs"
                assert main_module.app.redoc_url == "/redoc"
                assert main_module.app.openapi_url == "/openapi.json"
        finally:
            importlib.reload(main_module)

    def test_cors_middleware_added_when_origins_configured(self):
        import webhooks.main as main_module
        from webhooks.config import Settings

        env = {"CORS_ORIGINS": '["https://example.com"]'}
        with patch.dict("os.environ", env, clear=True):
            configured = Settings(_env_file=None)
        try:
            with patch("webhooks.config.settings", configured):
                importlib.reload(main_module)
                names = [m.cls.__name__ for m in main_module.app.user_middleware]
                assert "CORSMiddleware" in names
        finally:
            importlib.reload(main_module)

    def test_no_cors_middleware_by_default(self):
        from webhooks.main import app

        names = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" not in names
