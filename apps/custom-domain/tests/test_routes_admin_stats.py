# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/routes/admin/stats.py - Unit tests with mocks."""

from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient


class TestOverviewStats:
    """Tests for overview stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_overview_stats(self, admin_client: AsyncClient, mock_db_session):
        """Test getting overview statistics."""
        # Mock scalar to return counts
        mock_db_session.scalar.return_value = 0

        response = await admin_client.get("/api/v1/admin/stats/overview")
        assert response.status_code == 200
        data = response.json()
        assert "domains" in data
        assert "clients" in data
        assert "templates" in data

    @pytest.mark.asyncio
    async def test_get_overview_stats_unauthorized(self, auth_client: AsyncClient):
        """Test getting stats without admin scope."""
        response = await auth_client.get("/api/v1/admin/stats/overview")
        assert response.status_code in (401, 403)


class TestTopClients:
    """Tests for top clients endpoint."""

    @pytest.mark.asyncio
    async def test_get_top_clients(self, admin_client: AsyncClient, mock_db_session):
        """Test getting top clients."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/stats/top-clients")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_top_clients_with_limit(self, admin_client: AsyncClient, mock_db_session):
        """Test getting top clients with limit."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/stats/top-clients?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5


class TestRecentActivity:
    """Tests for recent activity endpoint."""

    @pytest.mark.asyncio
    async def test_get_recent_activity(self, admin_client: AsyncClient, mock_db_session):
        """Test getting recent activity."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/stats/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_recent_activity_with_limit(self, admin_client: AsyncClient, mock_db_session):
        """Test getting recent activity with limit."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/stats/recent-activity?limit=5")
        assert response.status_code == 200


class TestDashboard:
    """Tests for dashboard endpoint."""

    @pytest.mark.asyncio
    async def test_get_dashboard(self, admin_client: AsyncClient, mock_db_session):
        """Test getting dashboard data."""
        mock_db_session.scalar.return_value = 0

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/stats/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "overview" in data
        assert "top_clients" in data
        assert "recent_activity" in data

    @pytest.mark.asyncio
    async def test_get_dashboard_unauthorized(self, auth_client: AsyncClient):
        """Test getting dashboard without admin scope."""
        response = await auth_client.get("/api/v1/admin/stats/dashboard")
        assert response.status_code in (401, 403)
