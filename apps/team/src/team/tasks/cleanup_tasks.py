# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Cleanup tasks - purge old execution logs and stale workspaces."""

import logging
import shutil
from pathlib import Path
from uuid import UUID

from sqlalchemy import CursorResult, delete, select

from team.celery import celery_app
from team.config import get_settings
from team.database import async_session_factory
from team.models import ExecutionLog, Task
from team.tasks.utils import run_async

logger = logging.getLogger(__name__)


async def _cleanup(days_old: int) -> int:
    """Delete execution logs older than days_old days."""
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_old)

    async with async_session_factory() as session:
        result = await session.execute(delete(ExecutionLog).where(ExecutionLog.created_at < cutoff))
        await session.commit()
        cursor: CursorResult[tuple[()]] = result  # type: ignore[assignment]
        return cursor.rowcount or 0


@celery_app.task(name="team.tasks.cleanup_tasks.cleanup_old_logs")
def cleanup_old_logs(days_old: int = 90) -> dict:
    """Purge old execution logs.

    Runs every 24 hours via Celery beat.
    """
    logger.info(f"Cleaning up execution logs older than {days_old} days")
    count = run_async(_cleanup(days_old))
    logger.info(f"Deleted {count} old execution logs")
    return {"deleted": count}


async def _cleanup_stale_workspaces() -> int:
    """Remove workspace directories for tasks that are terminal or unknown."""
    workspace_base = Path(get_settings().workspace_dir).resolve()
    if not workspace_base.exists():
        return 0

    deleted = 0
    async with async_session_factory() as session:
        for entry in workspace_base.iterdir():
            if not entry.is_dir():
                continue
            # Only process UUID-named directories (task workspaces)
            try:
                task_id = UUID(entry.name)
            except ValueError:
                continue

            result = await session.execute(select(Task.status).where(Task.id == task_id))
            status = result.scalar_one_or_none()

            # Remove if task not found or in a terminal state (paused is NOT terminal)
            if status is None or status in ("completed", "failed", "cancelled"):
                try:
                    shutil.rmtree(entry)
                    deleted += 1
                except Exception:
                    logger.exception(f"Failed to remove stale workspace: {entry}")

    return deleted


@celery_app.task(name="team.tasks.cleanup_tasks.cleanup_stale_workspaces")
def cleanup_stale_workspaces() -> dict:
    """Remove orphaned task workspace directories.

    Safety net for workspaces not cleaned up by agent_runner's finally block.
    Runs every hour via Celery beat.
    """
    logger.info("Cleaning up stale workspace directories")
    count = run_async(_cleanup_stale_workspaces())
    logger.info(f"Deleted {count} stale workspace directories")
    return {"deleted": count}
