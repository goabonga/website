# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for cleanup tasks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from team.tasks.cleanup_tasks import (
    _cleanup,
    _cleanup_stale_workspaces,
    cleanup_old_logs,
    cleanup_stale_workspaces,
)


class TestCleanup:
    async def test_deletes_old_logs(self):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 42

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_cursor)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory):
            result = await _cleanup(90)

        assert result == 42

    async def test_zero_deleted(self):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_cursor)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory):
            result = await _cleanup(30)

        assert result == 0


def _fake_run_async(coro, return_value=0):
    """Close the coroutine to avoid 'was never awaited' warnings."""
    coro.close()
    return return_value


class TestCleanupOldLogs:
    def test_calls_cleanup(self):
        with patch(
            "team.tasks.cleanup_tasks.run_async",
            side_effect=lambda coro: _fake_run_async(coro, 10),
        ):
            result = cleanup_old_logs(days_old=30)

        assert result == {"deleted": 10}

    def test_default_days(self):
        with patch(
            "team.tasks.cleanup_tasks.run_async",
            side_effect=lambda coro: _fake_run_async(coro, 0),
        ):
            result = cleanup_old_logs()

        assert result == {"deleted": 0}


class TestCleanupStaleWorkspaces:
    async def test_removes_completed_task_workspace(self, tmp_path):
        task_id = uuid4()
        task_dir = tmp_path / str(task_id)
        task_dir.mkdir()
        (task_dir / "repo").mkdir()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "completed"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.cleanup_tasks.get_settings") as m,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await _cleanup_stale_workspaces()

        assert result == 1
        assert not task_dir.exists()

    async def test_removes_failed_task_workspace(self, tmp_path):
        task_id = uuid4()
        task_dir = tmp_path / str(task_id)
        task_dir.mkdir()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "failed"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.cleanup_tasks.get_settings") as m,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await _cleanup_stale_workspaces()

        assert result == 1

    async def test_removes_unknown_task_workspace(self, tmp_path):
        task_id = uuid4()
        task_dir = tmp_path / str(task_id)
        task_dir.mkdir()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # task not in DB

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.cleanup_tasks.get_settings") as m,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await _cleanup_stale_workspaces()

        assert result == 1

    async def test_skips_in_progress_task(self, tmp_path):
        task_id = uuid4()
        task_dir = tmp_path / str(task_id)
        task_dir.mkdir()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "in_progress"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.cleanup_tasks.get_settings") as m,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await _cleanup_stale_workspaces()

        assert result == 0
        assert task_dir.exists()

    async def test_skips_non_uuid_directories(self, tmp_path):
        (tmp_path / "not-a-uuid").mkdir()
        (tmp_path / "random-file.txt").write_text("hi")

        mock_session = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.cleanup_tasks.get_settings") as m,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await _cleanup_stale_workspaces()

        assert result == 0
        mock_session.execute.assert_not_called()

    async def test_returns_zero_when_workspace_missing(self, tmp_path):
        nonexistent = tmp_path / "nope"
        with patch("team.tasks.cleanup_tasks.get_settings") as m:
            m.return_value.workspace_dir = str(nonexistent)
            result = await _cleanup_stale_workspaces()

        assert result == 0

    async def test_logs_error_when_rmtree_fails(self, tmp_path):
        task_id = uuid4()
        task_dir = tmp_path / str(task_id)
        task_dir.mkdir()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "completed"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.cleanup_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.cleanup_tasks.get_settings") as m,
            patch("team.tasks.cleanup_tasks.shutil.rmtree", side_effect=OSError("denied")),
            patch("team.tasks.cleanup_tasks.logger") as mock_logger,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await _cleanup_stale_workspaces()

        assert result == 0
        mock_logger.exception.assert_called_once()


class TestCleanupStaleWorkspacesTask:
    def test_sync_wrapper(self):
        with patch(
            "team.tasks.cleanup_tasks.run_async",
            side_effect=lambda coro: _fake_run_async(coro, 3),
        ):
            result = cleanup_stale_workspaces()

        assert result == {"deleted": 3}
