# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for webhook tasks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from team.tasks.webhook_tasks import _process_event, process_webhook_event


def _make_task_mock():
    task = MagicMock()
    task.id = uuid4()
    task.team_id = uuid4()
    task.agent_id = uuid4()
    task.workflow_id = uuid4()
    task.status = "in_progress"
    task.output_data = {}
    task.updated_at = None
    return task


def _make_workflow_mock():
    wf = MagicMock()
    wf.id = uuid4()
    wf.status = "active"
    wf.config = {}
    wf.updated_at = None
    return wf


class TestTaskCompletedEvent:
    async def test_marks_task_completed(self):
        task = _make_task_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "agent.task.completed",
                    "task_id": str(task.id),
                    "result": {"answer": 42},
                }
            )

        assert task.status == "completed"
        assert task.output_data == {"answer": 42}
        mock_session.add.assert_called_once()

    async def test_missing_task_id(self):
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "agent.task.completed",
                }
            )

        mock_session.execute.assert_not_awaited()

    async def test_task_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "agent.task.completed",
                    "task_id": str(uuid4()),
                }
            )

        mock_session.add.assert_not_called()


class TestTaskFailedEvent:
    async def test_marks_task_failed(self):
        task = _make_task_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "agent.task.failed",
                    "task_id": str(task.id),
                    "error": "timeout",
                }
            )

        assert task.status == "failed"
        assert task.output_data == {"error": "timeout"}
        mock_session.add.assert_called_once()

    async def test_missing_task_id(self):
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "agent.task.failed",
                    "error": "crash",
                }
            )

        mock_session.execute.assert_not_awaited()

    async def test_task_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "agent.task.failed",
                    "task_id": str(uuid4()),
                }
            )

        mock_session.add.assert_not_called()


class TestWorkflowUpdatedEvent:
    async def test_updates_workflow_status(self):
        wf = _make_workflow_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = wf

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "workflow.updated",
                    "workflow_id": str(wf.id),
                    "status": "completed",
                }
            )

        assert wf.status == "completed"

    async def test_updates_workflow_config(self):
        wf = _make_workflow_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = wf

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "workflow.updated",
                    "workflow_id": str(wf.id),
                    "config": {"timeout": 600},
                }
            )

        assert wf.config == {"timeout": 600}

    async def test_missing_workflow_id(self):
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "workflow.updated",
                    "status": "paused",
                }
            )

        mock_session.execute.assert_not_awaited()

    async def test_workflow_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event(
                {
                    "event": "workflow.updated",
                    "workflow_id": str(uuid4()),
                }
            )


class TestUnknownEvent:
    async def test_unknown_event(self):
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event({"event": "unknown.event"})

        mock_session.execute.assert_not_awaited()

    async def test_missing_event_field(self):
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.webhook_tasks.async_session_factory", return_value=mock_factory):
            await _process_event({"data": "no event field"})

        mock_session.execute.assert_not_awaited()


def _fake_run_async(coro, return_value=None):
    """Close the coroutine to avoid 'was never awaited' warnings."""
    coro.close()
    return return_value


class TestProcessWebhookEvent:
    def test_calls_process_event(self):
        with patch(
            "team.tasks.webhook_tasks.run_async",
            side_effect=lambda coro: _fake_run_async(coro),
        ):
            result = process_webhook_event({"event": "agent.task.completed"})

        assert result == {"status": "processed", "event": "agent.task.completed"}

    def test_returns_none_event_when_missing(self):
        with patch(
            "team.tasks.webhook_tasks.run_async",
            side_effect=lambda coro: _fake_run_async(coro),
        ):
            result = process_webhook_event({"data": "no event"})

        assert result == {"status": "processed", "event": None}
