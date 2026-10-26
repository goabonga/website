# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""create_task tool — spawn sub-tasks in the same team."""

from sqlalchemy import select

from team.models import Agent, Task
from team.services.tool_service import ToolService

DEFINITION = {
    "name": "create_task",
    "description": (
        "Create a new sub-task in the current team. "
        "Set input_data.role to route the task to a specific agent. "
        "The role must match an existing agent role exactly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Task title"},
            "description": {"type": "string", "description": "Task description"},
            "input_data": {
                "type": "object",
                "description": "Task input parameters. Use 'role' to target a specific agent.",
            },
            "priority": {
                "type": "integer",
                "description": "Priority (higher = first)",
                "default": 0,
            },
        },
        "required": ["title"],
    },
}


@ToolService.register("create_task", DEFINITION)
async def create_task(params: dict, context: dict) -> dict:
    """Create a pending task in the same team."""
    session = context["db"]
    team_id = context["team_id"]
    input_data = params.get("input_data", {})

    # Inject creator agent info into input_data
    creator_id = context.get("agent_id")
    if creator_id:
        result = await session.execute(select(Agent.name).where(Agent.id == creator_id))
        creator_name = result.scalar_one_or_none()
        input_data["created_by_agent_id"] = str(creator_id)
        if creator_name:
            input_data["created_by_agent_name"] = creator_name

    # Validate role against active agents
    desired_role = input_data.get("role")
    if desired_role:
        result = await session.execute(
            select(Agent.role).where(Agent.team_id == team_id, Agent.is_active.is_(True)).distinct()
        )
        available_roles = sorted(r for (r,) in result.all())

        if desired_role not in available_roles:
            return {
                "error": f"No agent with role '{desired_role}'",
                "available_roles": available_roles,
            }

    task = Task(
        team_id=team_id,
        title=params["title"],
        description=params.get("description", ""),
        input_data=input_data,
        priority=params.get("priority", 0),
        workflow_id=context.get("workflow_id"),
    )
    session.add(task)
    await session.flush()
    return {"task_id": str(task.id), "title": params["title"], "status": "pending"}
