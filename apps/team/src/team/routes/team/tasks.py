# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Task management routes."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import AgentState, Conversation, ExecutionLog, Task, Team
from team.schemas import TaskCreate, TaskResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/{team_id}/tasks", tags=["Platform - Tasks"])


async def get_task_or_404(task_id: str, team_id: str, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.team_id == team_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


async def get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    return team


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    team_id: str,
    data: TaskCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    """Create a new task.

    If agent_id is provided, the task is created in the assigned status.
    """
    await get_team_or_404(team_id, db)

    task = Task(
        team_id=team_id,
        title=data.title,
        description=data.description or "",
        status="assigned" if data.agent_id else "pending",
        priority=data.priority,
        input_data=data.input_data,
        output_data={},
        workflow_id=data.workflow_id,
        agent_id=data.agent_id,
    )

    db.add(task)
    await db.flush()
    await db.refresh(task)

    logger.info("Task %s created for team %s (status=%s)", task.id, team_id, task.status)

    return task


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    team_id: str,
    task_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    """Cancel a task.

    - pending/assigned/paused: immediately set to cancelled
    - in_progress: set to cancelled; agent runner loop will detect on next iteration
    - completed/failed/cancelled: returns 409 Conflict
    """
    await get_team_or_404(team_id, db)
    task = await get_task_or_404(task_id, team_id, db)

    if task.status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task cannot be cancelled: current status is '{task.status}'",
        )

    previous_status = task.status
    task.status = "cancelled"
    task.output_data = {"cancelled_from": previous_status}
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)

    # Reset agent state if agent was working on this task
    if task.agent_id:
        state_result = await db.execute(
            select(AgentState).where(AgentState.agent_id == task.agent_id)
        )
        agent_state = state_result.scalar_one_or_none()
        if agent_state and agent_state.current_task == task.title:
            agent_state.state = "idle"
            agent_state.current_task = ""
            agent_state.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)

    # Cancel active conversation for this task
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.slug == f"task-{task.id}",
            Conversation.status == "active",
        )
    )
    conversation = conv_result.scalar_one_or_none()
    if conversation:
        conversation.status = "cancelled"
        conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)

    db.add(
        ExecutionLog(
            team_id=task.team_id,
            task_id=task.id,
            agent_id=task.agent_id,
            workflow_id=task.workflow_id,
            event_type="task.cancelled",
            details={"previous_status": previous_status, "task_title": task.title},
        )
    )

    await db.flush()
    await db.refresh(task)

    logger.info("Task %s cancelled (was %s) for team %s", task.id, previous_status, team_id)

    return task
