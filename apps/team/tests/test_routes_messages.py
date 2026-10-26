# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for message routes."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_conversation_mock():
    conv = MagicMock()
    conv.id = uuid4()
    conv.slug = "general"
    return conv


def _make_agent_mock():
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "DevAgent"
    return agent


class TestPostMessage:
    @pytest.mark.asyncio
    async def test_post_message_returns_200(self, auth_client: AsyncClient, mock_db_session):
        conv = _make_conversation_mock()
        agent = _make_agent_mock()

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        mock_db_session.execute = AsyncMock(side_effect=[conv_result, agent_result])

        response = await auth_client.post(
            f"/platform/conversations/{conv.id}/messages",
            json={
                "agent_id": str(agent.id),
                "type": "message",
                "content": {"text": "Hello"},
                "text": "Hello",
                "visibility": "public",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_post_message_conversation_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/conversations/{uuid4()}/messages",
            json={
                "agent_id": str(uuid4()),
                "type": "message",
                "content": {},
                "text": "Hello",
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_post_message_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        conv = _make_conversation_mock()

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[conv_result, agent_result])

        response = await auth_client.post(
            f"/platform/conversations/{conv.id}/messages",
            json={
                "agent_id": str(uuid4()),
                "type": "message",
                "content": {},
                "text": "Hello",
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_post_message_requires_auth(self, client: AsyncClient):
        response = await client.post(
            f"/platform/conversations/{uuid4()}/messages",
            json={"agent_id": str(uuid4()), "text": "Hello"},
        )
        assert response.status_code == 401


class TestListMessages:
    @pytest.mark.asyncio
    async def test_list_messages_returns_200(self, auth_client: AsyncClient, mock_db_session):
        conv = _make_conversation_mock()

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[conv_result, list_result])

        response = await auth_client.get(f"/platform/conversations/{conv.id}/messages")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_messages_conversation_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/conversations/{uuid4()}/messages")
        assert response.status_code == 404
