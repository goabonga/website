# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.routes.health module."""

from analytics.routes.health import HealthResponse, health_check


class TestHealthCheck:
    """Tests for health_check endpoint."""

    async def test_returns_healthy_status(self):
        result = await health_check()
        assert isinstance(result, HealthResponse)
        assert result.status == "healthy"


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_serialization(self):
        response = HealthResponse(status="healthy")
        assert response.model_dump() == {"status": "healthy"}
