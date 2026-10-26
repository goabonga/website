# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Skill activation tool — loads full skill instructions for an agent."""

import logging

from sqlalchemy import select

from team.models.skill import Skill
from team.services.tool_service import ToolService

logger = logging.getLogger(__name__)

ACTIVATE_SKILL_DEFINITION = {
    "name": "activate_skill",
    "description": (
        "Activate an agent skill by name to load its full instructions. "
        "Use this when a task matches one of your available skills. "
        "The skill's detailed instructions will be returned for you to follow."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "The name of the skill to activate (from <available_skills>)",
            },
        },
        "required": ["skill_name"],
    },
}


@ToolService.register("activate_skill", ACTIVATE_SKILL_DEFINITION)
async def activate_skill(params: dict, context: dict) -> dict:
    """Load the full skill content for the requesting agent."""
    session = context["db"]
    agent_id = context["agent_id"]
    skill_name = params["skill_name"]

    result = await session.execute(
        select(Skill).where(
            Skill.agent_id == agent_id,
            Skill.name == skill_name,
            Skill.is_active.is_(True),
        )
    )
    skill = result.scalar_one_or_none()

    if not skill:
        return {
            "error": f"Skill '{skill_name}' not found or inactive",
            "hint": "Check available skills in your system prompt",
        }

    logger.info("Agent %s activated skill '%s' (%s)", agent_id, skill_name, skill.id)

    return {
        "skill_name": skill.name,
        "description": skill.description,
        "instructions": skill.content,
        "allowed_tools": skill.allowed_tools,
        "metadata": skill.metadata_,
    }
