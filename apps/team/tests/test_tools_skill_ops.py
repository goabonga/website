# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for activate_skill tool."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _make_skill_mock(**kwargs):
    skill = MagicMock()
    skill.id = kwargs.get("id", uuid4())
    skill.name = kwargs.get("name", "code-review")
    skill.description = kwargs.get("description", "Review code changes.")
    skill.content = kwargs.get("content", "# Code Review\n\n1. Check style\n2. Check logic")
    skill.allowed_tools = kwargs.get("allowed_tools", ["github_create_pr"])
    skill.metadata_ = kwargs.get("metadata_", {"author": "test"})
    return skill


class TestActivateSkill:
    async def test_returns_skill_content(self):
        skill = _make_skill_mock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        agent_id = uuid4()
        ctx = {"db": mock_session, "agent_id": agent_id}

        result = await ToolService._registry["activate_skill"][0](
            {"skill_name": "code-review"}, ctx
        )

        assert result["skill_name"] == "code-review"
        assert result["description"] == "Review code changes."
        assert result["instructions"] == "# Code Review\n\n1. Check style\n2. Check logic"
        assert result["allowed_tools"] == ["github_create_pr"]
        assert result["metadata"] == {"author": "test"}

    async def test_returns_error_when_skill_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        ctx = {"db": mock_session, "agent_id": uuid4()}

        result = await ToolService._registry["activate_skill"][0](
            {"skill_name": "nonexistent"}, ctx
        )

        assert "error" in result
        assert "nonexistent" in result["error"]
        assert "hint" in result
