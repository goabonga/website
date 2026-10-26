# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mta_sts.main module."""

import httpx
from mta_sts import __version__
from mta_sts.main import HealthResponse, app, health_check


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class TestAppConfiguration:
    """Tests for FastAPI app configuration."""

    def test_app_title(self):
        assert app.title == "mta-sts"

    def test_app_version(self):
        assert app.version == __version__

    def test_docs_disabled(self):
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    async def test_docs_endpoints_return_404(self):
        async with make_client() as client:
            for path in ("/docs", "/redoc", "/openapi.json"):
                assert (await client.get(path)).status_code == 404

    async def test_unknown_path_returns_404(self):
        async with make_client() as client:
            assert (await client.get("/unknown")).status_code == 404


class TestHealthCheck:
    """Tests for the health endpoint."""

    async def test_returns_healthy_status(self):
        result = await health_check()
        assert isinstance(result, HealthResponse)
        assert result.status == "healthy"

    async def test_http_response(self):
        async with make_client() as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_serialization(self):
        assert HealthResponse(status="healthy").model_dump() == {"status": "healthy"}


class TestVersion:
    """Tests for package version."""

    def test_version_format(self):
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)
