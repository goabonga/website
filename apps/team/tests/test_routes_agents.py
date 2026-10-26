# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for agent management routes."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_team_mock():
    team = MagicMock()
    team.id = uuid4()
    return team


def _make_agent_mock(team_id):
    agent = MagicMock()
    agent.id = uuid4()
    agent.team_id = team_id
    agent.name = "DevAgent"
    agent.role = "developer"
    agent.description = ""
    agent.system_prompt = ""
    agent.model = "gpt-4o"
    agent.provider = "openai"
    agent.config = {}
    agent.is_active = True
    agent.created_at = "2024-01-01T00:00:00"
    return agent


class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_create_agent_returns_201(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_team_result)

        response = await auth_client.post(
            f"/platform/{team_id}/agents",
            json={"name": "DevAgent", "role": "developer"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "DevAgent"
        assert data["role"] == "developer"

    @pytest.mark.asyncio
    async def test_create_agent_with_provider(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_team_result)

        response = await auth_client.post(
            f"/platform/{team_id}/agents",
            json={
                "name": "ClaudeAgent",
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "provider": "anthropic",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["provider"] == "anthropic"
        assert data["model"] == "claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    async def test_create_agent_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{uuid4()}/agents",
            json={"name": "DevAgent", "role": "developer"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_agent_requires_auth(self, client: AsyncClient):
        response = await client.post(
            f"/platform/{uuid4()}/agents",
            json={"name": "DevAgent", "role": "developer"},
        )
        assert response.status_code == 401


class TestListAgents:
    @pytest.mark.asyncio
    async def test_list_agents_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        # First call: get_team_or_404, Second call: list query
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[team_result, list_result])

        response = await auth_client.get(f"/platform/{team_id}/agents")
        assert response.status_code == 200
        assert response.json() == []


class TestGetAgent:
    @pytest.mark.asyncio
    async def test_get_agent_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent = _make_agent_mock(team_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/{team_id}/agents/{agent.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/{uuid4()}/agents/{uuid4()}")
        assert response.status_code == 404


class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_update_agent_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent = _make_agent_mock(team_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/{team_id}/agents/{agent.id}",
            json={"name": "UpdatedAgent"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/{uuid4()}/agents/{uuid4()}",
            json={"name": "UpdatedAgent"},
        )
        assert response.status_code == 404


class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_delete_agent_returns_204(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent = _make_agent_mock(team_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/{team_id}/agents/{agent.id}")
        assert response.status_code == 204
        mock_db_session.delete.assert_called_once_with(agent)

    @pytest.mark.asyncio
    async def test_delete_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/{uuid4()}/agents/{uuid4()}")
        assert response.status_code == 404
