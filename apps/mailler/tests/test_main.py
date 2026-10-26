# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.main module."""

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
