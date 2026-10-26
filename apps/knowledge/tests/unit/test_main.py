# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for the application wiring in knowledge/main.py and internal.py."""

from unittest.mock import MagicMock, patch

from httpx import AsyncClient


class TestLifespan:
    """Test the lifespan context manager."""

    async def test_lifespan_logs_startup_and_shutdown(self):
        with (
            patch("knowledge.main.logger") as mock_logger,
            patch("knowledge.main.settings") as mock_settings,
        ):
            mock_settings.app_name = "Test App"
            from knowledge.main import lifespan

            async with lifespan(MagicMock()):
                assert mock_logger.info.call_count == 1
            assert mock_logger.info.call_count == 2


class TestApplicationWiring:
    """Test that the public and internal applications are exposed."""

    async def test_public_docs_disabled_by_default(self, client: AsyncClient):
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 404

    async def test_internal_docs_are_served(self, client: AsyncClient):
        response = await client.get("/internal/docs")
        assert response.status_code == 200
        response = await client.get("/internal/openapi.json")
        assert response.status_code == 200
        assert "/health" not in response.json()["paths"]

    async def test_health_is_served_by_internal_app(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    async def test_cors_headers_on_preflight(self, client: AsyncClient):
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
