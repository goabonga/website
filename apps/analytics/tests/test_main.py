# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.main module."""

import logging
from unittest.mock import AsyncMock


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


class TestLifespan:
    """Tests for lifespan context manager."""

    async def test_lifespan_logs_startup_and_shutdown(self, caplog):
        from analytics.main import lifespan

        with caplog.at_level(logging.INFO, logger="analytics.main"):
            async with lifespan(AsyncMock()):
                assert "Starting Analytics" in caplog.text
        assert "Shutting down Analytics" in caplog.text
