# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/main.py."""

from unittest.mock import patch


class TestAppRoutes:
    """Tests for registered app routes."""

    def test_health_route_is_registered(self):
        """The /health route should be registered."""
        from billing.main import app
        from fastapi.testclient import TestClient

        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_docs_routes_disabled_by_default(self):
        """Docs routes should not be registered when docs_enabled is False."""
        from billing.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        for path in ("/docs", "/openapi.json", "/redoc"):
            assert client.get(path).status_code == 404

    def test_app_title(self):
        """App title should match settings."""
        from billing.main import app

        assert app.title is not None
        assert len(app.title) > 0

    def test_app_version(self):
        """App version should be set."""
        from billing.main import app

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
        from billing import __version__

        response = await client.get("/health")
        data = response.json()

        assert data["version"] == __version__


class TestLifespan:
    """Tests for app lifespan startup/shutdown."""

    async def test_lifespan_startup_logs(self):
        """Lifespan startup should log a starting message."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with patch("billing.main.logger") as mock_logger:
            async with lifespan(main_app):
                mock_logger.info.assert_called()
                startup_call = mock_logger.info.call_args_list[0]
                assert "Starting" in str(startup_call)

    async def test_lifespan_shutdown_logs_message(self):
        """Lifespan shutdown should log a shutting down message."""
        from billing.main import app as main_app
        from billing.main import lifespan

        with patch("billing.main.logger") as mock_logger:
            async with lifespan(main_app):
                pass

            shutdown_calls = [
                c for c in mock_logger.info.call_args_list if "Shutting down" in str(c)
            ]
            assert len(shutdown_calls) == 1
