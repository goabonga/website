# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Task dispatch - route pending tasks to agents."""

import logging

from sqlalchemy import select

from team.celery import celery_app
from team.database import async_session_factory
from team.models import Agent, ExecutionLog, Task, Team
from team.tasks.utils import run_async

logger = logging.getLogger(__name__)


async def _dispatch(batch_size: int) -> tuple[int, list[str]]:
    """Query pending tasks and assign them to matching agents."""
    dispatched = 0
    assigned_task_ids: list[str] = []

    async with async_session_factory() as session:
        # Get all active teams
        result = await session.execute(select(Team).where(Team.is_active.is_(True)))
        teams = list(result.scalars().all())

        for team in teams:
            # Get pending and paused tasks for this team
            task_result = await session.execute(
                select(Task)
                .where(Task.team_id == team.id, Task.status.in_(["pending", "paused"]))
                .order_by(Task.priority.desc(), Task.created_at.asc())
                .limit(batch_size)
            )
            pending_tasks = list(task_result.scalars().all())

            if not pending_tasks:
                continue

            # Get active agents for this team
            agent_result = await session.execute(
                select(Agent).where(Agent.team_id == team.id, Agent.is_active.is_(True))
            )
            agents = list(agent_result.scalars().all())

            if not agents:
                logger.warning(f"Team {team.id} has pending tasks but no active agents")
                continue

            # Build role -> agent lookup
            agents_by_role: dict[str, Agent] = {}
            for agent in agents:
                agents_by_role.setdefault(agent.role, agent)

            for task in pending_tasks:
                # Try to match by role from input_data
                desired_role = task.input_data.get("role") if task.input_data else None
                matched = agents_by_role.get(desired_role) if desired_role else None

                if desired_role and matched is None:
                    available = sorted(agents_by_role.keys())
                    logger.warning(
                        f"Task '{task.title}' requests role '{desired_role}' "
                        f"but no agent matches. Available roles: {available}. "
                        f"Skipping assignment."
                    )
                    continue

                assigned_agent = matched if matched is not None else agents[0]

                previous_status = task.status
                task.agent_id = assigned_agent.id
                task.status = "assigned"
                if previous_status == "paused":
                    task.output_data = {}

                log = ExecutionLog(
                    team_id=team.id,
                    task_id=task.id,
                    agent_id=assigned_agent.id,
                    event_type="task.assigned",
                    details={"task_title": task.title, "agent_name": assigned_agent.name},
                )
                session.add(log)
                assigned_task_ids.append(str(task.id))
                dispatched += 1

            logger.info(f"Dispatched {len(pending_tasks)} tasks for team {team.name}")

        await session.commit()

    return dispatched, assigned_task_ids


@celery_app.task(name="team.tasks.dispatch_tasks.dispatch_tasks")
def dispatch_tasks(batch_size: int = 50) -> dict:
    """Route pending tasks to available agents.

    Runs every 5 minutes via Celery beat.
    """
    from team.tasks.agent_runner import run_agent_task

    logger.info(f"Dispatching tasks (batch_size={batch_size})")
    count, task_ids = run_async(_dispatch(batch_size))

    # Trigger agent runner for each assigned task
    for tid in task_ids:
        run_agent_task.delay(tid)

    logger.info(f"Dispatched {count} tasks")
    return {"dispatched": count}
