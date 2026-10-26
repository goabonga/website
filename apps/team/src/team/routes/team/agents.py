# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Agent management routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import Agent, Team
from team.schemas import AgentCreate, AgentResponse, AgentUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/{team_id}/agents", tags=["Platform - Agents"])


async def get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    return team


async def get_agent_or_404(agent_id: str, team_id: str, db: AsyncSession) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.team_id == team_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    team_id: str,
    data: AgentCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Agent:
    """Create a new AI agent."""

    await get_team_or_404(team_id, db)

    agent = Agent(
        team_id=team_id,
        name=data.name,
        role=data.role,
        description=data.description,
        system_prompt=data.system_prompt,
        model=data.model,
        provider=data.provider,
        config=data.config,
        is_active=True,
    )

    db.add(agent)
    await db.flush()
    await db.refresh(agent)

    logger.info(f"Created agent: {agent.name} ({agent.id}) role={agent.role}")

    return agent


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    team_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Agent]:
    """List agents for a team."""

    await get_team_or_404(team_id, db)

    query = (
        select(Agent)
        .where(Agent.team_id == team_id)
        .order_by(Agent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    team_id: str,
    agent_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Agent:
    """Get agent by ID."""

    return await get_agent_or_404(agent_id, team_id, db)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    team_id: str,
    agent_id: str,
    data: AgentUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Agent:
    """Update agent configuration."""

    agent = await get_agent_or_404(agent_id, team_id, db)

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.flush()
    await db.refresh(agent)

    logger.info(f"Updated agent: {agent.name} ({agent.id})")

    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    team_id: str,
    agent_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete an agent."""

    agent = await get_agent_or_404(agent_id, team_id, db)

    await db.delete(agent)
    await db.flush()

    logger.info(f"Deleted agent: {agent.name} ({agent.id})")
