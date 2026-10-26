# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auto-orchestration task."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from team.tasks.auto_orchestrate import (
    ORCHESTRATOR_PROMPT,
    _auto_orchestrate,
    auto_orchestrate,
)


def _make_team():
    team = MagicMock()
    team.id = uuid4()
    team.slug = "goabonga"
    team.is_active = True
    team.config = {}
    return team


def _make_agent(role="ceo"):
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "CEO Agent"
    agent.role = role
    agent.is_active = True
    return agent


def _mock_session_factory(session):
    factory = MagicMock()
    factory.__aenter__ = AsyncMock(return_value=session)
    factory.__aexit__ = AsyncMock(return_value=False)
    return factory


class TestAutoOrchestrate:
    async def test_team_not_found(self):
        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=team_result)

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("unknown-team")

        assert result["status"] == "skipped"
        assert result["reason"] == "team_not_found"

    async def test_no_orchestrator_agent(self):
        team = _make_team()
        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[team_result, agent_result])

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "skipped"
        assert result["reason"] == "no_orchestrator_agent"

    async def test_already_active_task(self):
        team = _make_team()
        agent = _make_agent()
        existing_task = MagicMock()

        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_task

        mock_session.execute = AsyncMock(side_effect=[team_result, agent_result, existing_result])

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "skipped"
        assert result["reason"] == "already_active"

    async def test_creates_orchestration_task(self):
        team = _make_team()
        agent = _make_agent()

        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None  # no active task

        mock_session.execute = AsyncMock(side_effect=[team_result, agent_result, existing_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "created"
        assert "task_id" in result
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

        # Verify the task that was added
        added_task = mock_session.add.call_args[0][0]
        assert added_task.team_id == team.id
        assert added_task.title == "Autonomous team check-in"
        assert added_task.priority == 100
        assert added_task.input_data["role"] == "ceo"
        assert added_task.input_data["prompt"] == ORCHESTRATOR_PROMPT

    async def test_disabled_orchestration(self):
        """Returns skipped when orchestration is disabled in team config."""
        team = _make_team()
        team.config = {"orchestration": {"enabled": False}}

        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        mock_session.execute = AsyncMock(return_value=team_result)

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "skipped"
        assert result["reason"] == "disabled"

    async def test_too_soon_skips(self):
        """Skips when last orchestration was more recent than schedule_minutes."""
        team = _make_team()
        team.config = {"orchestration": {"schedule_minutes": 30}}
        agent = _make_agent()

        # Last orchestration task completed 10 minutes ago
        last_task = MagicMock()
        last_task.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)

        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None  # no active task
        last_result = MagicMock()
        last_result.scalar_one_or_none.return_value = last_task

        mock_session.execute = AsyncMock(
            side_effect=[team_result, agent_result, existing_result, last_result]
        )

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "skipped"
        assert result["reason"] == "too_soon"

    async def test_schedule_elapsed_creates_task(self):
        """Creates task when enough time has passed since last orchestration."""
        team = _make_team()
        team.config = {"orchestration": {"schedule_minutes": 15}}
        agent = _make_agent()

        # Last orchestration task completed 20 minutes ago
        last_task = MagicMock()
        last_task.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=20)

        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        last_result = MagicMock()
        last_result.scalar_one_or_none.return_value = last_task

        mock_session.execute = AsyncMock(
            side_effect=[team_result, agent_result, existing_result, last_result]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "created"
        mock_session.add.assert_called_once()

    async def test_schedule_no_previous_task(self):
        """Creates task when schedule_minutes is set but no previous run exists."""
        team = _make_team()
        team.config = {"orchestration": {"schedule_minutes": 15}}
        agent = _make_agent()

        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        last_result = MagicMock()
        last_result.scalar_one_or_none.return_value = None  # no previous task

        mock_session.execute = AsyncMock(
            side_effect=[team_result, agent_result, existing_result, last_result]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "created"
        mock_session.add.assert_called_once()

    async def test_custom_prompt(self):
        """Uses custom prompt from team config."""
        team = _make_team()
        team.config = {"orchestration": {"prompt": "Custom check-in prompt"}}
        agent = _make_agent()

        mock_session = AsyncMock()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[team_result, agent_result, existing_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "team.tasks.auto_orchestrate.async_session_factory",
            return_value=_mock_session_factory(mock_session),
        ):
            result = await _auto_orchestrate("goabonga")

        assert result["status"] == "created"
        added_task = mock_session.add.call_args[0][0]
        assert added_task.input_data["prompt"] == "Custom check-in prompt"


def _fake_run_async(coro, return_value=None):
    """Close the coroutine to avoid 'was never awaited' warnings."""
    coro.close()
    return return_value


class TestAutoOrchestrateCeleryTask:
    def test_calls_run_async(self):
        expected = {"status": "created", "task_id": "abc"}
        with patch(
            "team.tasks.auto_orchestrate.run_async",
            side_effect=lambda coro: _fake_run_async(coro, expected),
        ):
            result = auto_orchestrate("goabonga")

        assert result == expected

    def test_default_team_slug(self):
        expected = {"status": "skipped", "reason": "team_not_found"}
        with patch(
            "team.tasks.auto_orchestrate.run_async",
            side_effect=lambda coro: _fake_run_async(coro, expected),
        ):
            result = auto_orchestrate()

        assert result == expected
