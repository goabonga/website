# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for main FastAPI application."""

import pytest


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        from internal.main import health_check

        result = await health_check()
        assert result.status == "healthy"


class TestHealthResponse:
    def test_model(self):
        from internal.main import HealthResponse

        resp = HealthResponse(status="ok")
        assert resp.status == "ok"


class TestAppCreated:
    def test_app_exists(self):
        from internal.main import app

        assert app is not None
        assert app.title is not None
