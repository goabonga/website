# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for save_memory tool."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


class TestSaveMemory:
    async def test_saves_entry_with_embedding(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        async def mock_refresh(obj, **kwargs):
            obj.id = uuid4()

        mock_session.refresh = mock_refresh

        ctx = {"db": mock_session, "team_id": uuid4(), "agent_id": uuid4()}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            result = await ToolService._registry["save_memory"][0](
                {"content": "Important fact about the project"}, ctx
            )

        assert result["saved"] is True
        assert "memory_id" in result
        assert result["content_length"] == len("Important fact about the project")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    async def test_saves_with_extra_metadata(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        async def mock_refresh(obj, **kwargs):
            obj.id = uuid4()

        mock_session.refresh = mock_refresh

        ctx = {"db": mock_session, "team_id": uuid4(), "agent_id": uuid4()}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            result = await ToolService._registry["save_memory"][0](
                {"content": "Deployment note", "extra": {"category": "devops"}}, ctx
            )

        assert result["saved"] is True
        added_entry = mock_session.add.call_args[0][0]
        assert added_entry.extra == {"category": "devops"}

    async def test_saves_without_agent_id(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        async def mock_refresh(obj, **kwargs):
            obj.id = uuid4()

        mock_session.refresh = mock_refresh

        ctx = {"db": mock_session, "team_id": uuid4()}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            result = await ToolService._registry["save_memory"][0](
                {"content": "Team-level memory"}, ctx
            )

        assert result["saved"] is True
        added_entry = mock_session.add.call_args[0][0]
        assert added_entry.agent_id is None

    async def test_default_extra_is_empty_dict(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        async def mock_refresh(obj, **kwargs):
            obj.id = uuid4()

        mock_session.refresh = mock_refresh

        ctx = {"db": mock_session, "team_id": uuid4(), "agent_id": uuid4()}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ):
            result = await ToolService._registry["save_memory"][0]({"content": "No extra"}, ctx)

        assert result["saved"] is True
        added_entry = mock_session.add.call_args[0][0]
        assert added_entry.extra == {}
