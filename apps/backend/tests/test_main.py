# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.main module."""

from backend import __version__
from backend.config import settings
from backend.main import app
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
