# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for update_memory and delete_memory tools."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


class TestUpdateMemory:
    async def test_update_content_and_reembed(self):
        entry = MagicMock()
        entry.id = uuid4()
        entry.content = "Old content"
        entry.extra = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entry

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        ctx = {"db": mock_session, "team_id": uuid4()}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.2] * 1536,
        ):
            result = await ToolService._registry["update_memory"][0](
                {"memory_id": str(entry.id), "content": "New content"}, ctx
            )

        assert result["updated"] is True
        assert entry.content == "New content"
        assert entry.embedding == [0.2] * 1536
        mock_session.flush.assert_awaited_once()

    async def test_update_with_extra(self):
        entry = MagicMock()
        entry.id = uuid4()
        entry.extra = {"old": True}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entry

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        ctx = {"db": mock_session, "team_id": uuid4()}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            result = await ToolService._registry["update_memory"][0](
                {"memory_id": str(entry.id), "content": "Updated", "extra": {"new": True}}, ctx
            )

        assert result["updated"] is True
        assert entry.extra == {"new": True}

    async def test_update_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        ctx = {"db": mock_session, "team_id": uuid4()}

        result = await ToolService._registry["update_memory"][0](
            {"memory_id": str(uuid4()), "content": "New"}, ctx
        )

        assert "error" in result
        assert "not found" in result["error"].lower()


class TestDeleteMemory:
    async def test_delete_success(self):
        entry = MagicMock()
        entry.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entry

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        ctx = {"db": mock_session, "team_id": uuid4()}

        result = await ToolService._registry["delete_memory"][0]({"memory_id": str(entry.id)}, ctx)

        assert result["deleted"] is True
        mock_session.delete.assert_awaited_once_with(entry)
        mock_session.flush.assert_awaited_once()

    async def test_delete_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        ctx = {"db": mock_session, "team_id": uuid4()}

        result = await ToolService._registry["delete_memory"][0]({"memory_id": str(uuid4())}, ctx)

        assert "error" in result
        assert "not found" in result["error"].lower()
