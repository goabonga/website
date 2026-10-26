# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for orchestrator service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from team.services.orchestrator_service import OrchestratorService


class TestOrchestratorService:
    @pytest.fixture
    def db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, db):
        return OrchestratorService(db)

    @pytest.mark.asyncio
    async def test_init_stores_db(self, db):
        service = OrchestratorService(db)
        assert service.db is db

    @pytest.mark.asyncio
    async def test_get_pending_tasks(self, service, db):
        team_id = uuid4()
        mock_task = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_task]
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_pending_tasks(team_id)
        assert result == [mock_task]

    @pytest.mark.asyncio
    async def test_get_pending_tasks_with_limit(self, service, db):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_pending_tasks(team_id, limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_assign_task(self, service, db):
        task = MagicMock()
        task.id = uuid4()
        agent_id = uuid4()

        result = await service.assign_task(task, agent_id)

        assert task.agent_id == agent_id
        assert task.status == "assigned"
        db.flush.assert_called_once()
        assert result is task
