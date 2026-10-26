# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GET /api/v1/stats route."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


class TestGetStats:
    """Tests for GET /api/v1/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/stats should return totals, by_provider, and by_date."""
        # Mock total query result
        total_row = MagicMock()
        total_row.sent = 10
        total_row.delivered = 8
        total_row.bounced = 1
        total_row.failed = 1

        total_result = MagicMock()
        total_result.one.return_value = total_row

        # Mock by_provider query result
        provider_result = MagicMock()
        provider_result.all.return_value = []

        # Mock by_date query result
        date_result = MagicMock()
        date_result.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[total_result, provider_result, date_result]
        )

        response = await auth_client.get("/api/v1/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "by_provider" in data
        assert "by_date" in data
        assert data["total"]["sent"] == 10
        assert data["total"]["delivered"] == 8
        assert data["total"]["bounced"] == 1
        assert data["total"]["failed"] == 1
        assert data["by_provider"] == {}
        assert data["by_date"] == []

    @pytest.mark.asyncio
    async def test_get_stats_with_dates(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/stats with explicit start_date and end_date."""
        total_row = MagicMock()
        total_row.sent = 5
        total_row.delivered = 4
        total_row.bounced = 0
        total_row.failed = 1
        total_result = MagicMock()
        total_result.one.return_value = total_row

        provider_result = MagicMock()
        provider_result.all.return_value = []

        date_result = MagicMock()
        date_result.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[total_result, provider_result, date_result]
        )

        response = await auth_client.get("/api/v1/stats?start_date=2024-01-01&end_date=2024-01-31")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_stats_with_provider_filter(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/stats?provider=brevo triggers the provider filter branch."""
        total_row = MagicMock()
        total_row.sent = 3
        total_row.delivered = 2
        total_row.bounced = 0
        total_row.failed = 1
        total_result = MagicMock()
        total_result.one.return_value = total_row

        provider_result = MagicMock()
        provider_result.all.return_value = []

        date_result = MagicMock()
        date_result.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[total_result, provider_result, date_result]
        )

        response = await auth_client.get("/api/v1/stats?provider=brevo")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_stats_with_by_provider_data(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/stats returns populated by_provider and by_date data."""
        total_row = MagicMock()
        total_row.sent = 10
        total_row.delivered = 8
        total_row.bounced = 1
        total_row.failed = 1
        total_result = MagicMock()
        total_result.one.return_value = total_row

        # Provider row
        prow = MagicMock()
        prow.provider = "brevo"
        prow.sent = 10
        prow.delivered = 8
        prow.bounced = 1
        prow.failed = 1
        provider_result = MagicMock()
        provider_result.all.return_value = [prow]

        # Date row
        drow = MagicMock()
        drow.email_date = "2024-01-15"
        drow.sent = 5
        drow.delivered = 4
        drow.bounced = 0
        drow.failed = 1
        date_result = MagicMock()
        date_result.all.return_value = [drow]

        mock_db_session.execute = AsyncMock(
            side_effect=[total_result, provider_result, date_result]
        )

        response = await auth_client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "brevo" in data["by_provider"]
        assert len(data["by_date"]) == 1


def _empty_results():
    total_row = MagicMock(sent=0, delivered=0, bounced=0, failed=0)
    total_result = MagicMock()
    total_result.one.return_value = total_row
    provider_result = MagicMock()
    provider_result.all.return_value = []
    date_result = MagicMock()
    date_result.all.return_value = []
    return [total_result, provider_result, date_result]


class TestStatsAreScopedToTheCallingClient:
    """Statistics only count the emails of the calling client."""

    @pytest.mark.asyncio
    async def test_every_query_is_restricted_to_the_client(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_db_session.execute = AsyncMock(side_effect=_empty_results())
        response = await auth_client.get("/api/v1/stats")
        assert response.status_code == 200
        for call in mock_db_session.execute.await_args_list:
            assert call.args[0].compile().params["client_id_1"] == "test-client-id"

    @pytest.mark.asyncio
    async def test_another_client_is_forbidden(self, auth_client: AsyncClient, mock_db_session):
        response = await auth_client.get("/api/v1/stats?client_id=other-client")
        assert response.status_code == 403
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_counts_every_client(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_empty_results())
        response = await admin_client.get("/api/v1/stats")
        assert response.status_code == 200
        for call in mock_db_session.execute.await_args_list:
            assert "client_id_1" not in call.args[0].compile().params

    @pytest.mark.asyncio
    async def test_admin_can_narrow_to_one_client(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_empty_results())
        response = await admin_client.get("/api/v1/stats?client_id=other-client")
        assert response.status_code == 200
        for call in mock_db_session.execute.await_args_list:
            assert call.args[0].compile().params["client_id_1"] == "other-client"
