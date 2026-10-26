# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for memory service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from team.services.memory_service import MemoryService


class TestMemoryService:
    @pytest.fixture
    def db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, db):
        return MemoryService(db)

    @pytest.mark.asyncio
    async def test_init_stores_db(self, db):
        service = MemoryService(db)
        assert service.db is db

    @pytest.mark.asyncio
    async def test_get_recent_entries(self, service, db):
        team_id = uuid4()
        mock_entry = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_entry]
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_recent_entries(team_id)
        assert result == [mock_entry]

    @pytest.mark.asyncio
    async def test_get_recent_entries_with_limit(self, service, db):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_recent_entries(team_id, limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_agent_memory(self, service, db):
        agent_id = uuid4()
        mock_entry = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_entry]
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_agent_memory(agent_id)
        assert result == [mock_entry]

    @pytest.mark.asyncio
    async def test_get_agent_memory_with_limit(self, service, db):
        agent_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_agent_memory(agent_id, limit=5)
        assert result == []
