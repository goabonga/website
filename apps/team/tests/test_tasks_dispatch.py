# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for dispatch tasks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from team.tasks.dispatch_tasks import _dispatch, dispatch_tasks


def _make_team():
    team = MagicMock()
    team.id = uuid4()
    team.name = "Engineering"
    team.is_active = True
    return team


def _make_agent(role="developer"):
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "DevAgent"
    agent.role = role
    agent.is_active = True
    return agent


def _make_task(input_data=None):
    task = MagicMock()
    task.id = uuid4()
    task.title = "Fix bug"
    task.status = "pending"
    task.priority = 0
    task.input_data = input_data or {}
    return task


class TestDispatch:
    async def test_dispatches_tasks_to_agents(self):
        team = _make_team()
        agent = _make_agent()
        task = _make_task()

        mock_session = AsyncMock()

        # team query
        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        # pending tasks query
        task_result = MagicMock()
        task_result.scalars.return_value.all.return_value = [task]

        # agents query
        agent_result = MagicMock()
        agent_result.scalars.return_value.all.return_value = [agent]

        mock_session.execute = AsyncMock(side_effect=[team_result, task_result, agent_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.dispatch_tasks.async_session_factory", return_value=mock_factory):
            count, task_ids = await _dispatch(50)

        assert count == 1
        assert len(task_ids) == 1
        assert task.status == "assigned"
        assert task.agent_id == agent.id

    async def test_dispatches_by_role(self):
        team = _make_team()
        dev_agent = _make_agent("developer")
        sre_agent = _make_agent("sre")
        task = _make_task(input_data={"role": "sre"})

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        task_result = MagicMock()
        task_result.scalars.return_value.all.return_value = [task]

        agent_result = MagicMock()
        agent_result.scalars.return_value.all.return_value = [dev_agent, sre_agent]

        mock_session.execute = AsyncMock(side_effect=[team_result, task_result, agent_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.dispatch_tasks.async_session_factory", return_value=mock_factory):
            count, task_ids = await _dispatch(50)

        assert count == 1
        assert len(task_ids) == 1
        assert task.agent_id == sre_agent.id

    async def test_no_pending_tasks(self):
        team = _make_team()

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        task_result = MagicMock()
        task_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[team_result, task_result])
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.dispatch_tasks.async_session_factory", return_value=mock_factory):
            count, task_ids = await _dispatch(50)

        assert count == 0
        assert task_ids == []

    async def test_skips_task_with_unknown_role(self):
        team = _make_team()
        agent = _make_agent("developer")
        task = _make_task(input_data={"role": "security_engineer"})

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        task_result = MagicMock()
        task_result.scalars.return_value.all.return_value = [task]

        agent_result = MagicMock()
        agent_result.scalars.return_value.all.return_value = [agent]

        mock_session.execute = AsyncMock(side_effect=[team_result, task_result, agent_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.dispatch_tasks.async_session_factory", return_value=mock_factory):
            count, task_ids = await _dispatch(50)

        assert count == 0
        assert task_ids == []
        assert task.status == "pending"  # not changed

    async def test_dispatches_paused_tasks(self):
        """Paused tasks (e.g. from credit errors) are re-dispatched."""
        team = _make_team()
        agent = _make_agent()
        task = _make_task()
        task.status = "paused"
        task.output_data = {"error": "credit balance is too low"}

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        task_result = MagicMock()
        task_result.scalars.return_value.all.return_value = [task]

        agent_result = MagicMock()
        agent_result.scalars.return_value.all.return_value = [agent]

        mock_session.execute = AsyncMock(side_effect=[team_result, task_result, agent_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.dispatch_tasks.async_session_factory", return_value=mock_factory):
            count, task_ids = await _dispatch(50)

        assert count == 1
        assert task.status == "assigned"
        assert task.output_data == {}  # cleared on re-dispatch

    async def test_no_active_agents(self):
        team = _make_team()
        task = _make_task()

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        task_result = MagicMock()
        task_result.scalars.return_value.all.return_value = [task]

        agent_result = MagicMock()
        agent_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[team_result, task_result, agent_result])
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.dispatch_tasks.async_session_factory", return_value=mock_factory):
            count, task_ids = await _dispatch(50)

        assert count == 0
        assert task_ids == []


def _fake_run_async(coro, return_value=(0, [])):
    """Close the coroutine to avoid 'was never awaited' warnings."""
    coro.close()
    return return_value


class TestDispatchTask:
    def test_calls_dispatch(self):
        mock_runner = MagicMock()
        with (
            patch(
                "team.tasks.dispatch_tasks.run_async",
                side_effect=lambda coro: _fake_run_async(coro, (5, ["t1", "t2"])),
            ),
            patch(
                "team.tasks.agent_runner.run_agent_task",
                mock_runner,
            ),
        ):
            result = dispatch_tasks(batch_size=10)

        assert result == {"dispatched": 5}
        assert mock_runner.delay.call_count == 2
