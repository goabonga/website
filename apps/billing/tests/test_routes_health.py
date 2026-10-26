# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for health check route."""

import pytest
from billing import __version__
from httpx import AsyncClient


class TestHealthCheck:
    """Tests for GET /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_200(self, client: AsyncClient):
        """GET /health should return 200 with status=healthy and correct version."""
        response = await client.get("/health")

        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == __version__

    @pytest.mark.asyncio
    async def test_health_check_response_structure(self, client: AsyncClient):
        """GET /health response should only contain status and version fields."""
        response = await client.get("/health")

        data = response.json()
        assert set(data.keys()) == {"status", "version"}

    @pytest.mark.asyncio
    async def test_health_check_no_auth_required(self, client: AsyncClient):
        """GET /health should work without authentication."""
        # client fixture has no auth headers
        response = await client.get("/health")

        assert response.status_code == 200
