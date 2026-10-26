# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for webhooks.main module."""

import importlib
from contextlib import contextmanager
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient


@contextmanager
def _reloaded_app(env):
    """Reload webhooks.main with settings built from the given environment."""
    import webhooks.main as main_module
    from webhooks.config import Settings

    with patch.dict("os.environ", env, clear=True):
        configured = Settings(_env_file=None)
    try:
        with patch("webhooks.config.settings", configured):
            importlib.reload(main_module)
            yield main_module.app
    finally:
        importlib.reload(main_module)


async def _post(app, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, content=b"{}")


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


class TestLifespan:
    """Tests for application lifespan context manager."""

    async def test_lifespan_calls_setup_logging_and_logs(self):
        from webhooks.main import app, lifespan

        with (
            patch("webhooks.main.setup_logging") as mock_setup,
            patch("webhooks.main.logger") as mock_logger,
        ):
            async with lifespan(app):
                mock_setup.assert_called_once()
                mock_logger.info.assert_any_call("Webhooks service starting")
            mock_logger.info.assert_any_call("Webhooks service shutting down")

    async def test_lifespan_uses_configured_log_level(self):
        from webhooks.main import app, lifespan

        with (
            patch("webhooks.main.setup_logging") as mock_setup,
            patch("webhooks.main.settings") as mock_settings,
        ):
            mock_settings.log_level = "DEBUG"
            async with lifespan(app):
                pass
        mock_setup.assert_called_once_with(level="DEBUG")


class TestBrevoRegistration:
    """Tests for conditional registration of the Brevo route."""

    async def test_route_not_registered_by_default(self):
        from webhooks.main import app

        response = await _post(app, "/webhooks/brevo")
        assert response.status_code == 404

    async def test_route_registered_when_enabled(self):
        with _reloaded_app({"BREVO_ENABLED": "true"}) as app:
            # Registered but not wired to an internal API yet: 503, not 404.
            response = await _post(app, "/webhooks/brevo")
        assert response.status_code == 503


class TestSESRegistration:
    """Tests for conditional registration of the SES route."""

    async def test_route_not_registered_by_default(self):
        from webhooks.main import app

        response = await _post(app, "/webhooks/ses")
        assert response.status_code == 404

    async def test_route_registered_when_enabled(self):
        with _reloaded_app({"SES_ENABLED": "true"}) as app:
            # Registered but not wired to an internal API yet: 503, not 404.
            response = await _post(app, "/webhooks/ses")
        assert response.status_code == 503


class TestStripeRegistration:
    """Tests for conditional registration of the Stripe route."""

    async def test_route_not_registered_by_default(self):
        from webhooks.main import app

        response = await _post(app, "/webhooks/stripe")
        assert response.status_code == 404

    async def test_route_registered_when_enabled(self):
        with _reloaded_app({"STRIPE_ENABLED": "true"}) as app:
            # Registered but not wired to an internal API yet: 503, not 404.
            response = await _post(app, "/webhooks/stripe")
        assert response.status_code == 503
