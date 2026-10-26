# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for memory management routes."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_team_mock():
    team = MagicMock()
    team.id = uuid4()
    return team


def _make_entry_mock(**kwargs):
    entry = MagicMock()
    entry.id = kwargs.get("id", uuid4())
    entry.team_id = kwargs.get("team_id", uuid4())
    entry.agent_id = kwargs.get("agent_id")
    entry.conversation_id = kwargs.get("conversation_id")
    entry.content = kwargs.get("content", "Some memory")
    entry.extra = kwargs.get("extra", {})
    entry.created_at = "2026-01-01T00:00:00"
    return entry


class TestListMemory:
    @pytest.mark.asyncio
    async def test_list_memory_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[team_result, list_result])

        response = await auth_client.get(f"/platform/{team_id}/memory")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_memory_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/{uuid4()}/memory")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_memory_requires_auth(self, client: AsyncClient):
        response = await client.get(f"/platform/{uuid4()}/memory")
        assert response.status_code == 401


class TestCreateMemoryEntry:
    @pytest.mark.asyncio
    async def test_create_memory_entry_returns_201(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "team.routes.team.memory.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            response = await auth_client.post(
                f"/platform/{team_id}/memory",
                json={"content": "Important context about the project"},
            )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_memory_entry_team_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{uuid4()}/memory",
            json={"content": "Important context"},
        )
        assert response.status_code == 404


class TestUpdateMemoryEntry:
    @pytest.mark.asyncio
    async def test_update_memory_entry_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        entry = _make_entry_mock(team_id=team_id, content="Old content")

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        mock_db_session.execute = AsyncMock(side_effect=[team_result, entry_result])

        with patch(
            "team.routes.team.memory.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.2] * 1536,
        ):
            response = await auth_client.patch(
                f"/platform/{team_id}/memory/{entry.id}",
                json={"content": "Updated content"},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_memory_entry_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, entry_result])

        response = await auth_client.patch(
            f"/platform/{team_id}/memory/{uuid4()}",
            json={"content": "Updated"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_memory_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/{uuid4()}/memory/{uuid4()}",
            json={"content": "Updated"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_memory_extra_only(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        entry = _make_entry_mock(team_id=team_id)

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        mock_db_session.execute = AsyncMock(side_effect=[team_result, entry_result])

        response = await auth_client.patch(
            f"/platform/{team_id}/memory/{entry.id}",
            json={"extra": {"tag": "updated"}},
        )
        assert response.status_code == 200


class TestDeleteMemoryEntry:
    @pytest.mark.asyncio
    async def test_delete_memory_entry_returns_204(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        entry = _make_entry_mock(team_id=team_id)

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        mock_db_session.execute = AsyncMock(side_effect=[team_result, entry_result])

        response = await auth_client.delete(
            f"/platform/{team_id}/memory/{entry.id}",
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_memory_entry_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, entry_result])

        response = await auth_client.delete(
            f"/platform/{team_id}/memory/{uuid4()}",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_memory_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(
            f"/platform/{uuid4()}/memory/{uuid4()}",
        )
        assert response.status_code == 404
