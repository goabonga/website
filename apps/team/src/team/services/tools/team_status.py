# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""team_status tool — introspect team state for autonomous orchestration."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from team.models import Agent, AgentState, Task
from team.services.tool_service import ToolService

DEFINITION = {
    "name": "team_status",
    "description": "Get the current status of the team: agents, tasks summary, and recent activity.",
    "parameters": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "description": "Look back period in hours for recent activity",
                "default": 24,
            },
        },
    },
}


@ToolService.register("team_status", DEFINITION)
async def team_status(params: dict, context: dict) -> dict:
    """Get team status: agents, task counts by status, recent completions."""
    session = context["db"]
    team_id = context["team_id"]
    hours = params.get("hours", 24)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)

    # Agent summary
    agents_result = await session.execute(
        select(Agent).where(Agent.team_id == team_id, Agent.is_active.is_(True))
    )
    agents = list(agents_result.scalars().all())

    agent_info = []
    for agent in agents:
        # Get agent state if exists
        state_result = await session.execute(
            select(AgentState).where(AgentState.agent_id == agent.id)
        )
        state = state_result.scalar_one_or_none()
        agent_info.append(
            {
                "name": agent.name,
                "role": agent.role,
                "state": state.state if state else "idle",
                "current_task": state.current_task if state else "",
            }
        )

    # Task counts by status
    counts_result = await session.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.team_id == team_id)
        .group_by(Task.status)
    )
    task_counts = dict(counts_result.all())

    # Recently completed tasks
    completed_result = await session.execute(
        select(Task)
        .where(
            Task.team_id == team_id,
            Task.status.in_(["completed", "failed"]),
            Task.updated_at >= since,
        )
        .order_by(Task.updated_at.desc())
        .limit(10)
    )
    recent = [
        {
            "title": t.title,
            "status": t.status,
            "output_summary": (t.output_data.get("content", "")[:200] if t.output_data else ""),
        }
        for t in completed_result.scalars().all()
    ]

    # Pending tasks waiting
    pending_result = await session.execute(
        select(Task)
        .where(Task.team_id == team_id, Task.status == "pending")
        .order_by(Task.priority.desc(), Task.created_at.asc())
        .limit(10)
    )
    pending = [
        {"title": t.title, "priority": t.priority, "description": t.description[:200]}
        for t in pending_result.scalars().all()
    ]

    return {
        "agents": agent_info,
        "task_counts": task_counts,
        "recent_activity": recent,
        "pending_tasks": pending,
    }
