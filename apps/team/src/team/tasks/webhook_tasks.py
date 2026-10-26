# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Process orchestration events via Celery worker."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from team.celery import celery_app
from team.database import async_session_factory
from team.models import ExecutionLog, Task, Workflow
from team.tasks.utils import run_async

logger = logging.getLogger(__name__)


async def _process_event(payload: dict) -> None:
    """Dispatch the event to the appropriate handler."""
    event_type = payload.get("event")
    logger.info(f"Processing webhook event: {event_type}")

    async with async_session_factory() as session:
        if event_type == "agent.task.completed":
            await _handle_task_completed(payload, session)
        elif event_type == "agent.task.failed":
            await _handle_task_failed(payload, session)
        elif event_type == "workflow.updated":
            await _handle_workflow_updated(payload, session)
        else:
            logger.warning(f"Unknown webhook event: {event_type}")

        await session.commit()


async def _handle_task_completed(payload: dict, session) -> None:
    """Mark task as completed, store output, create execution log."""
    task_id = payload.get("task_id")
    if not task_id:
        logger.warning("task.completed event missing task_id")
        return

    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning(f"Task {task_id} not found for completion event")
        return

    task.status = "completed"
    task.output_data = payload.get("result", {})
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)

    log = ExecutionLog(
        team_id=task.team_id,
        task_id=task.id,
        agent_id=task.agent_id,
        workflow_id=task.workflow_id,
        event_type="agent.task.completed",
        details={"output": task.output_data},
    )
    session.add(log)
    logger.info(f"Task {task_id} marked as completed")


async def _handle_task_failed(payload: dict, session) -> None:
    """Mark task as failed, store error, create execution log."""
    task_id = payload.get("task_id")
    if not task_id:
        logger.warning("task.failed event missing task_id")
        return

    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        logger.warning(f"Task {task_id} not found for failure event")
        return

    task.status = "failed"
    task.output_data = {"error": payload.get("error", "unknown")}
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)

    log = ExecutionLog(
        team_id=task.team_id,
        task_id=task.id,
        agent_id=task.agent_id,
        workflow_id=task.workflow_id,
        event_type="agent.task.failed",
        details={"error": payload.get("error", "unknown")},
    )
    session.add(log)
    logger.info(f"Task {task_id} marked as failed")


async def _handle_workflow_updated(payload: dict, session) -> None:
    """Update workflow status and/or config."""
    workflow_id = payload.get("workflow_id")
    if not workflow_id:
        logger.warning("workflow.updated event missing workflow_id")
        return

    result = await session.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        logger.warning(f"Workflow {workflow_id} not found for update event")
        return

    if "status" in payload:
        workflow.status = payload["status"]
    if "config" in payload:
        workflow.config = payload["config"]

    workflow.updated_at = datetime.now(UTC).replace(tzinfo=None)
    logger.info(f"Workflow {workflow_id} updated via webhook")


@celery_app.task(name="team.tasks.webhook_tasks.process_webhook_event")
def process_webhook_event(payload: dict) -> dict:
    """Process an orchestration event.

    Called on-demand via process_webhook_event.delay(payload).
    """
    event_type = payload.get("event")
    logger.info(f"Received webhook event: {event_type}")
    run_async(_process_event(payload))
    logger.info(f"Processed webhook event: {event_type}")
    return {"status": "processed", "event": event_type}
