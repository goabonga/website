# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for agent service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from team.services.agent_service import AgentService


class TestAgentService:
    @pytest.fixture
    def db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, db):
        return AgentService(db)

    @pytest.mark.asyncio
    async def test_init_stores_db(self, db):
        service = AgentService(db)
        assert service.db is db

    @pytest.mark.asyncio
    async def test_get_active_agents(self, service, db):
        team_id = uuid4()
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_agent]
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_active_agents(team_id)
        assert result == [mock_agent]
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_active_agents_empty(self, service, db):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_active_agents(team_id)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_agent_by_role_found(self, service, db):
        team_id = uuid4()
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_agent
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_agent_by_role(team_id, "developer")
        assert result is mock_agent

    @pytest.mark.asyncio
    async def test_get_agent_by_role_not_found(self, service, db):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_agent_by_role(team_id, "nonexistent")
        assert result is None
