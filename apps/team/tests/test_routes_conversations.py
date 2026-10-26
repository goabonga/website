# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for conversation management routes."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_conversation_mock():
    conv = MagicMock()
    conv.id = uuid4()
    conv.team_id = uuid4()
    conv.slug = "general"
    conv.title = "General"
    conv.type = "general"
    conv.status = "active"
    conv.extra = {}
    conv.created_at = "2024-01-01T00:00:00"
    conv.updated_at = "2024-01-01T00:00:00"
    return conv


def _make_agent_mock():
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "DevAgent"
    return agent


class TestCreateConversation:
    @pytest.mark.asyncio
    async def test_create_conversation_returns_201(self, auth_client: AsyncClient, mock_db_session):
        response = await auth_client.post(
            "/platform/conversations",
            json={"slug": "general", "title": "General"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "general"
        assert data["title"] == "General"

    @pytest.mark.asyncio
    async def test_create_conversation_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/platform/conversations",
            json={"slug": "general", "title": "General"},
        )
        assert response.status_code == 401


class TestListConversations:
    @pytest.mark.asyncio
    async def test_list_conversations_returns_200(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get("/platform/conversations")
        assert response.status_code == 200
        assert response.json() == []


class TestGetConversation:
    @pytest.mark.asyncio
    async def test_get_conversation_returns_200(self, auth_client: AsyncClient, mock_db_session):
        conv = _make_conversation_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/conversations/{conv.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/conversations/{uuid4()}")
        assert response.status_code == 404


class TestAddAgentToConversation:
    @pytest.mark.asyncio
    async def test_add_agent_returns_204(self, auth_client: AsyncClient, mock_db_session):
        conv = _make_conversation_mock()
        agent = _make_agent_mock()

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        mock_db_session.execute = AsyncMock(side_effect=[conv_result, agent_result])

        response = await auth_client.post(f"/platform/conversations/{conv.id}/agents/{agent.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_add_agent_conversation_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(f"/platform/conversations/{uuid4()}/agents/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_agent_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        conv = _make_conversation_mock()
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[conv_result, agent_result])

        response = await auth_client.post(f"/platform/conversations/{conv.id}/agents/{uuid4()}")
        assert response.status_code == 404


class TestDeleteConversation:
    @pytest.mark.asyncio
    async def test_delete_conversation_returns_204(self, auth_client: AsyncClient, mock_db_session):
        conv = _make_conversation_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/conversations/{conv.id}")
        assert response.status_code == 204
        mock_db_session.delete.assert_called_once_with(conv)

    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/conversations/{uuid4()}")
        assert response.status_code == 404
