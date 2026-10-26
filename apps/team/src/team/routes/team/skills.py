# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Agent skill management routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import Agent, Skill, Team
from team.schemas.skill import SkillCreate, SkillResponse, SkillSummaryResponse, SkillUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/platform/{team_id}/agents/{agent_id}/skills",
    tags=["Platform - Agent Skills"],
)


async def _get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


async def _get_agent_or_404(agent_id: str, team_id: str, db: AsyncSession) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.team_id == team_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def _get_skill_or_404(skill_id: str, agent_id: str, db: AsyncSession) -> Skill:
    result = await db.execute(select(Skill).where(Skill.id == skill_id, Skill.agent_id == agent_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return skill


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    team_id: str,
    agent_id: str,
    data: SkillCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Skill:
    """Create a new skill for an agent."""
    await _get_team_or_404(team_id, db)
    await _get_agent_or_404(agent_id, team_id, db)

    existing = await db.execute(
        select(Skill).where(Skill.agent_id == agent_id, Skill.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill with name '{data.name}' already exists for this agent",
        )

    skill = Skill(
        agent_id=agent_id,
        team_id=team_id,
        name=data.name,
        description=data.description,
        content=data.content,
        license=data.license,
        compatibility=data.compatibility,
        metadata_=data.metadata,
        allowed_tools=data.allowed_tools,
        is_active=data.is_active,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)

    logger.info("Created skill '%s' (%s) for agent %s", skill.name, skill.id, agent_id)
    return skill


@router.get("", response_model=list[SkillSummaryResponse])
async def list_skills(
    team_id: str,
    agent_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Skill]:
    """List skills for an agent (name + description only)."""
    await _get_team_or_404(team_id, db)
    await _get_agent_or_404(agent_id, team_id, db)

    query = (
        select(Skill)
        .where(Skill.agent_id == agent_id)
        .order_by(Skill.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    team_id: str,
    agent_id: str,
    skill_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Skill:
    """Get a skill by ID (includes full content)."""
    await _get_team_or_404(team_id, db)
    await _get_agent_or_404(agent_id, team_id, db)
    return await _get_skill_or_404(skill_id, agent_id, db)


@router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    team_id: str,
    agent_id: str,
    skill_id: str,
    data: SkillUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Skill:
    """Update a skill."""
    await _get_team_or_404(team_id, db)
    await _get_agent_or_404(agent_id, team_id, db)
    skill = await _get_skill_or_404(skill_id, agent_id, db)

    update_data = data.model_dump(exclude_unset=True, by_alias=False)
    # Map 'metadata' key from schema to 'metadata_' attribute on model
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for field_name, value in update_data.items():
        setattr(skill, field_name, value)

    await db.flush()
    await db.refresh(skill)

    logger.info("Updated skill '%s' (%s)", skill.name, skill.id)
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    team_id: str,
    agent_id: str,
    skill_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a skill."""
    await _get_team_or_404(team_id, db)
    await _get_agent_or_404(agent_id, team_id, db)
    skill = await _get_skill_or_404(skill_id, agent_id, db)

    await db.delete(skill)
    await db.flush()

    logger.info("Deleted skill '%s' (%s)", skill.name, skill.id)
