# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Auto-orchestration — periodically run the CEO agent to manage the team."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from team.celery import celery_app
from team.database import async_session_factory
from team.models import Agent, Task, Team
from team.tasks.utils import run_async

logger = logging.getLogger(__name__)

ORCHESTRATOR_ROLE = "ceo"

ORCHESTRATOR_PROMPT = (
    "You are running an autonomous check-in. Review the current team status and decide "
    "what actions to take. Use the `team_status` tool to see what agents are doing, "
    "what tasks are pending, completed, or failed.\n\n"
    "Based on the status, you may:\n"
    "- Create new tasks for agents using `create_task` (set the role in input_data)\n"
    "- Identify blockers or failed tasks that need attention\n"
    "- Prioritize work that is stalled\n"
    "- Coordinate between teams (e.g., ask QA to review after dev completes)\n\n"
    "If everything is running smoothly and there is nothing to do, simply report the status. "
    "Do NOT create tasks just for the sake of it — only when there is real work to be done.\n\n"
    "Always set the `role` field in `input_data` when creating tasks so they are routed "
    "to the right agent (e.g., developer, qa, devops, marketing)."
)


async def _auto_orchestrate(team_slug: str) -> dict:
    """Create an orchestration task for the CEO agent of a team."""
    async with async_session_factory() as session:
        # Find the team
        team_result = await session.execute(
            select(Team).where(Team.slug == team_slug, Team.is_active.is_(True))
        )
        team = team_result.scalar_one_or_none()
        if not team:
            logger.warning(f"Team '{team_slug}' not found or inactive")
            return {"status": "skipped", "reason": "team_not_found"}

        # Read orchestration config from team.config (all keys optional)
        orch_config = (team.config or {}).get("orchestration", {})

        if orch_config.get("enabled") is False:
            logger.info(f"Orchestration disabled for team '{team_slug}'")
            return {"status": "skipped", "reason": "disabled"}

        prompt = orch_config.get("prompt", ORCHESTRATOR_PROMPT)
        schedule_minutes = orch_config.get("schedule_minutes")

        # Find the orchestrator agent (CEO)
        agent_result = await session.execute(
            select(Agent).where(
                Agent.team_id == team.id,
                Agent.role == ORCHESTRATOR_ROLE,
                Agent.is_active.is_(True),
            )
        )
        agent = agent_result.scalar_one_or_none()
        if not agent:
            logger.warning(f"No active {ORCHESTRATOR_ROLE} agent in team '{team_slug}'")
            return {"status": "skipped", "reason": "no_orchestrator_agent"}

        # Check if there is already a pending/in_progress orchestration task
        existing_result = await session.execute(
            select(Task).where(
                Task.team_id == team.id,
                Task.title == "Autonomous team check-in",
                Task.status.in_(["pending", "assigned", "in_progress", "paused"]),
            )
        )
        if existing_result.scalar_one_or_none():
            logger.info(f"Orchestration task already active for team '{team_slug}'")
            return {"status": "skipped", "reason": "already_active"}

        # Respect per-team schedule: skip if last orchestration was too recent
        if schedule_minutes:
            last_result = await session.execute(
                select(Task)
                .where(
                    Task.team_id == team.id,
                    Task.title == "Autonomous team check-in",
                    Task.status.in_(["completed", "failed"]),
                )
                .order_by(Task.created_at.desc())
                .limit(1)
            )
            last_task = last_result.scalar_one_or_none()
            if last_task:
                elapsed = (
                    datetime.now(UTC).replace(tzinfo=None) - last_task.created_at
                ).total_seconds()
                if elapsed < schedule_minutes * 60:
                    logger.info(
                        f"Skipping orchestration for team '{team_slug}': "
                        f"{elapsed:.0f}s since last run (schedule={schedule_minutes}min)"
                    )
                    return {"status": "skipped", "reason": "too_soon"}

        # Create the orchestration task
        task = Task(
            team_id=team.id,
            title="Autonomous team check-in",
            description="Periodic autonomous review of team status by CEO.",
            input_data={
                "role": ORCHESTRATOR_ROLE,
                "prompt": prompt,
            },
            priority=100,  # High priority
        )
        session.add(task)
        await session.commit()

        logger.info(f"Created orchestration task for team '{team_slug}'")
        return {"status": "created", "task_id": str(task.id)}


@celery_app.task(name="team.tasks.auto_orchestrate.auto_orchestrate")
def auto_orchestrate(team_slug: str = "goabonga") -> dict:
    """Periodically trigger the CEO agent to review and manage the team.

    Runs via Celery beat. Creates a high-priority task for the CEO agent
    who then uses team_status + create_task to orchestrate work.

    Orchestration settings are read from team.config["orchestration"]:
      - enabled (bool): set to false to disable (default: true)
      - prompt (str): override the default orchestration prompt
      - schedule_minutes (int): minimum minutes between orchestration runs
    """
    logger.info(f"Auto-orchestrating team '{team_slug}'")
    return run_async(_auto_orchestrate(team_slug))
