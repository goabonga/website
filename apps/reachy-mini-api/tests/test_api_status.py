# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for reachy_mini_api/api/status.py."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reachy_mini_api.auth.dependencies import AuthContext
from reachy_mini_api.auth.jwks import jwks_manager
from reachy_mini_api.auth.models import User
from reachy_mini_api.main import app


@pytest.fixture
def mock_user():
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        name="Test",
        scopes=["reachy:status:read"],
        client_id="test-client",
    )
    return AuthContext(user=user)


class TestServerStatus:
    """Tests for GET /api/status/server endpoint."""

    @pytest.mark.asyncio
    async def test_get_server_status(self, mock_user):
        """Return server status information."""
        from reachy_mini_api.api.status import get_server_status

        with patch("reachy_mini_api.api.status.log_action"):
            result = await get_server_status(auth=mock_user)

        assert "timestamp" in result
        assert "hostname" in result
        assert "platform" in result
        assert "python_version" in result
        assert result["status"] == "online"

    @pytest.mark.asyncio
    async def test_server_status_logs_action(self, mock_user):
        """Log action when getting server status."""
        from reachy_mini_api.api.status import get_server_status

        with patch("reachy_mini_api.api.status.log_action") as mock_log:
            await get_server_status(auth=mock_user)
            mock_log.assert_called_once()


class TestServicesStatus:
    """Tests for GET /api/status/services endpoint."""

    @pytest.mark.asyncio
    async def test_get_services_status(self, mock_user):
        """Return services status."""
        from reachy_mini_api.api.status import get_services_status

        with patch("reachy_mini_api.api.status.log_action"):
            result = await get_services_status(auth=mock_user)

        assert "services" in result
        services = result["services"]
        assert len(services) == 3
        assert services[0]["name"] == "fastapi-api"
        assert services[0]["status"] == "running"
        assert services[0]["port"] == 8000

    @pytest.mark.asyncio
    async def test_services_status_logs_action(self, mock_user):
        """Log action when getting services status."""
        from reachy_mini_api.api.status import get_services_status

        with patch("reachy_mini_api.api.status.log_action") as mock_log:
            await get_services_status(auth=mock_user)
            mock_log.assert_called_once()


class TestStatusRoutes:
    """HTTP behaviour of the status routes, with the JWT validation faked."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def _get(self, client, path, scope):
        claims = {"sub": str(uuid4()), "scope": scope}
        with patch.object(jwks_manager, "validate_token", AsyncMock(return_value=claims)):
            return client.get(path, headers={"Authorization": "Bearer a.b.c"})

    def test_routes_are_mounted_under_api(self):
        paths = set(app.openapi()["paths"])
        assert {"/api/status/server", "/api/status/services"} <= paths

    @pytest.mark.parametrize("path", ["/api/status/server", "/api/status/services"])
    def test_requires_a_token(self, client, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", ["/api/status/server", "/api/status/services"])
    def test_requires_the_status_scope(self, client, path):
        assert self._get(client, path, "reachy:reports:read").status_code == 403

    def test_server_status_with_scope(self, client):
        response = self._get(client, "/api/status/server", "reachy:status:read")
        assert response.status_code == 200
        assert response.json()["status"] == "online"

    def test_services_status_with_scope(self, client):
        response = self._get(client, "/api/status/services", "reachy:status:read")
        assert response.status_code == 200
        assert len(response.json()["services"]) == 3
