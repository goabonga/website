# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the application object and the health endpoint."""

import re

from fastapi.testclient import TestClient
from reachy_mini_api import __version__
from reachy_mini_api.main import HealthResponse, app, health_check

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
