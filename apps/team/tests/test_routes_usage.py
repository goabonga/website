# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for usage reporting routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from team.routes.usage import _to_naive


class TestToNaive:
    def test_none_returns_utcnow(self):
        result = _to_naive(None)
        assert result.tzinfo is None

    def test_aware_datetime_stripped(self):
        aware = datetime(2024, 1, 1, tzinfo=UTC)
        result = _to_naive(aware)
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1)

    def test_naive_datetime_passthrough(self):
        naive = datetime(2024, 6, 15, 12, 30)
        result = _to_naive(naive)
        assert result is naive


def _make_team_mock():
    team = MagicMock()
    team.id = uuid4()
    return team


class TestReportUsage:
    @pytest.mark.asyncio
    async def test_report_usage_returns_201(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/usage/{team_id}/report",
            json={
                "agent_id": str(uuid4()),
                "action": "task.completed",
                "details": {"duration": 42},
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_report_usage_with_timestamp(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/usage/{team_id}/report",
            json={
                "agent_id": str(uuid4()),
                "action": "task.started",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_report_usage_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/usage/{uuid4()}/report",
            json={
                "agent_id": str(uuid4()),
                "action": "task.completed",
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_report_usage_requires_auth(self, client: AsyncClient):
        response = await client.post(
            f"/usage/{uuid4()}/report",
            json={
                "agent_id": str(uuid4()),
                "action": "task.completed",
            },
        )
        assert response.status_code == 401


class TestBatchReportUsage:
    @pytest.mark.asyncio
    async def test_batch_report_returns_201(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        agent_id = str(uuid4())
        response = await auth_client.post(
            f"/usage/{team_id}/batch",
            json={
                "events": [
                    {"agent_id": agent_id, "action": "task.started"},
                    {"agent_id": agent_id, "action": "task.completed"},
                ]
            },
        )
        assert response.status_code == 201
        assert response.json() == {"created": 2}

    @pytest.mark.asyncio
    async def test_batch_report_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/usage/{uuid4()}/batch",
            json={
                "events": [
                    {"agent_id": str(uuid4()), "action": "task.started"},
                ]
            },
        )
        assert response.status_code == 404
