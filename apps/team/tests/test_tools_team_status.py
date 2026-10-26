# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team_status tool."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _make_agent(name, role, state="idle", current_task=""):
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.name = name
    agent.role = role
    agent.is_active = True

    agent_state = MagicMock()
    agent_state.state = state
    agent_state.current_task = current_task
    return agent, agent_state


def _make_task(
    title, status="pending", priority=0, description="", output_data=None, updated_at=None
):
    task = MagicMock()
    task.title = title
    task.status = status
    task.priority = priority
    task.description = description
    task.output_data = output_data or {}
    task.updated_at = updated_at or datetime.now(UTC).replace(tzinfo=None)
    return task


class TestTeamStatus:
    async def test_status_with_agents_and_tasks(self):
        dev, dev_state = _make_agent(
            "Backend Dev", "developer", state="thinking", current_task="Build API"
        )
        qa, qa_state = _make_agent("QA", "qa")

        pending_task = _make_task("Write tests", priority=5, description="Unit tests for auth")
        completed_task = _make_task(
            "Build API", status="completed", output_data={"content": "Done building API"}
        )

        mock_session = AsyncMock()

        # agents query
        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = [dev, qa]

        # agent states
        dev_state_result = MagicMock()
        dev_state_result.scalar_one_or_none.return_value = dev_state
        qa_state_result = MagicMock()
        qa_state_result.scalar_one_or_none.return_value = qa_state

        # task counts
        counts_result = MagicMock()
        counts_result.all.return_value = [("pending", 3), ("completed", 10), ("failed", 1)]

        # recent activity
        recent_result = MagicMock()
        recent_result.scalars.return_value.all.return_value = [completed_task]

        # pending tasks
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = [pending_task]

        mock_session.execute = AsyncMock(
            side_effect=[
                agents_result,  # agents query
                dev_state_result,  # dev state
                qa_state_result,  # qa state
                counts_result,  # task counts
                recent_result,  # recent activity
                pending_result,  # pending tasks
            ]
        )

        context = {"db": mock_session, "team_id": uuid.uuid4()}
        result = await ToolService._registry["team_status"][0]({}, context)

        assert len(result["agents"]) == 2
        assert result["agents"][0]["name"] == "Backend Dev"
        assert result["agents"][0]["state"] == "thinking"
        assert result["agents"][0]["current_task"] == "Build API"
        assert result["agents"][1]["state"] == "idle"

        assert result["task_counts"]["pending"] == 3
        assert result["task_counts"]["completed"] == 10

        assert len(result["recent_activity"]) == 1
        assert result["recent_activity"][0]["title"] == "Build API"

        assert len(result["pending_tasks"]) == 1
        assert result["pending_tasks"][0]["title"] == "Write tests"

    async def test_status_no_agents(self):
        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = []
        counts_result = MagicMock()
        counts_result.all.return_value = []
        recent_result = MagicMock()
        recent_result.scalars.return_value.all.return_value = []
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[
                agents_result,
                counts_result,
                recent_result,
                pending_result,
            ]
        )

        context = {"db": mock_session, "team_id": uuid.uuid4()}
        result = await ToolService._registry["team_status"][0]({}, context)

        assert result["agents"] == []
        assert result["task_counts"] == {}

    async def test_status_agent_without_state(self):
        agent, _ = _make_agent("CTO", "cto")

        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = [agent]
        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None  # no AgentState row
        counts_result = MagicMock()
        counts_result.all.return_value = []
        recent_result = MagicMock()
        recent_result.scalars.return_value.all.return_value = []
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[
                agents_result,
                state_result,
                counts_result,
                recent_result,
                pending_result,
            ]
        )

        context = {"db": mock_session, "team_id": uuid.uuid4()}
        result = await ToolService._registry["team_status"][0]({}, context)

        assert result["agents"][0]["state"] == "idle"
        assert result["agents"][0]["current_task"] == ""

    async def test_status_custom_hours(self):
        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = []
        counts_result = MagicMock()
        counts_result.all.return_value = []
        recent_result = MagicMock()
        recent_result.scalars.return_value.all.return_value = []
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[
                agents_result,
                counts_result,
                recent_result,
                pending_result,
            ]
        )

        context = {"db": mock_session, "team_id": uuid.uuid4()}
        result = await ToolService._registry["team_status"][0]({"hours": 48}, context)

        assert "agents" in result

    async def test_status_output_truncation(self):
        long_output = "x" * 500
        task = _make_task("Long task", status="completed", output_data={"content": long_output})

        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = []
        counts_result = MagicMock()
        counts_result.all.return_value = []
        recent_result = MagicMock()
        recent_result.scalars.return_value.all.return_value = [task]
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[
                agents_result,
                counts_result,
                recent_result,
                pending_result,
            ]
        )

        context = {"db": mock_session, "team_id": uuid.uuid4()}
        result = await ToolService._registry["team_status"][0]({}, context)

        assert len(result["recent_activity"][0]["output_summary"]) == 200
