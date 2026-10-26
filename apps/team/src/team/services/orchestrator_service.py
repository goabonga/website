# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Orchestrator service for task routing and coordination."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.models import Task, Workflow

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Route tasks and coordinate agent workflows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_pending_tasks(self, team_id: UUID, limit: int = 50) -> list[Task]:
        """Get pending tasks ready for dispatch."""
        result = await self.db.execute(
            select(Task)
            .where(Task.team_id == team_id, Task.status == "pending")
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def assign_task(self, task: Task, agent_id: UUID) -> Task:
        """Assign a task to an agent."""
        task.agent_id = agent_id
        task.status = "assigned"
        await self.db.flush()
        logger.info(f"Assigned task {task.id} to agent {agent_id}")
        return task

    async def start_workflow(self, workflow: Workflow) -> list[Task]:
        """Activate a workflow and create tasks for initial steps (no dependencies)."""
        workflow.status = "active"
        steps = workflow.steps
        if not isinstance(steps, list):
            return []

        initial_tasks: list[Task] = []
        for step in steps:
            depends_on = step.get("depends_on", [])
            if not depends_on:
                task = Task(
                    team_id=workflow.team_id,
                    workflow_id=workflow.id,
                    title=step.get("name", step["id"]),
                    description=step.get("description", ""),
                    input_data={
                        **step.get("input_template", {}),
                        "step_id": step["id"],
                        "role": step.get("role"),
                    },
                    priority=step.get("priority", 0),
                )
                self.db.add(task)
                initial_tasks.append(task)

        await self.db.flush()
        return initial_tasks
