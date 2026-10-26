# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team-scoped conversation routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_team_mock():
    team = MagicMock()
    team.id = uuid4()
    return team


def _make_conversation_mock(team_id):
    conv = MagicMock()
    conv.id = uuid4()
    conv.team_id = team_id
    conv.slug = f"task-{uuid4()}"
    conv.title = "Task: Test"
    conv.type = "task"
    conv.status = "completed"
    conv.extra = {}
    conv.created_at = datetime.now(UTC)
    conv.updated_at = datetime.now(UTC)
    return conv


class TestListTeamConversations:
    @pytest.mark.asyncio
    async def test_list_conversations(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        team_mock = _make_team_mock()
        conv1 = _make_conversation_mock(team_id)
        conv2 = _make_conversation_mock(team_id)

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team_mock

        conv_result = MagicMock()
        conv_result.scalars.return_value.all.return_value = [conv1, conv2]

        mock_db_session.execute = AsyncMock(side_effect=[team_result, conv_result])

        response = await auth_client.get(f"/platform/{team_id}/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        team_mock = _make_team_mock()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team_mock

        conv_result = MagicMock()
        conv_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[team_result, conv_result])

        response = await auth_client.get(f"/platform/{team_id}/conversations")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_conversations_team_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/{uuid4()}/conversations")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_conversations_requires_auth(self, client: AsyncClient):
        response = await client.get(f"/platform/{uuid4()}/conversations")
        assert response.status_code == 401


class TestCountTeamConversations:
    @pytest.mark.asyncio
    async def test_count_conversations(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        team_mock = _make_team_mock()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team_mock

        count_result = MagicMock()
        count_result.scalar_one.return_value = 42

        mock_db_session.execute = AsyncMock(side_effect=[team_result, count_result])

        response = await auth_client.get(f"/platform/{team_id}/conversations/count")
        assert response.status_code == 200
        assert response.json() == {"count": 42}

    @pytest.mark.asyncio
    async def test_count_conversations_team_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/{uuid4()}/conversations/count")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_count_conversations_requires_auth(self, client: AsyncClient):
        response = await client.get(f"/platform/{uuid4()}/conversations/count")
        assert response.status_code == 401
