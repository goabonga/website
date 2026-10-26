# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/main.py."""

from unittest.mock import patch


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
