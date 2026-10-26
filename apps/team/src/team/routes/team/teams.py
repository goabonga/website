# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Team management routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import Team
from team.schemas import TeamCreate, TeamResponse, TeamUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/team", tags=["Platform - Teams"])


async def get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    return team


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    data: TeamCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Team:
    """Create a new team."""

    team = Team(
        name=data.name,
        slug=data.slug,
        description=data.description,
        config=data.config,
        is_active=True,
    )

    db.add(team)
    await db.flush()
    await db.refresh(team)

    logger.info(f"Created team: {team.name} ({team.id})")

    return team


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Team]:
    """List all teams."""

    query = select(Team).order_by(Team.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Team:
    """Get team by ID."""

    return await get_team_or_404(team_id, db)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    data: TeamUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Team:
    """Update team configuration."""

    team = await get_team_or_404(team_id, db)

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(team, field, value)

    await db.flush()
    await db.refresh(team)

    logger.info(f"Updated team: {team.name} ({team.id})")

    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a team."""

    team = await get_team_or_404(team_id, db)

    await db.delete(team)
    await db.flush()

    logger.info(f"Deleted team: {team.name} ({team.id})")
