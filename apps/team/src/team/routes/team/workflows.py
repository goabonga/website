# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Workflow management routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import Team, Workflow
from team.schemas import WorkflowCreate, WorkflowResponse, WorkflowUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/{team_id}/workflows", tags=["Platform - Workflows"])


async def get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    return team


async def get_workflow_or_404(workflow_id: str, team_id: str, db: AsyncSession) -> Workflow:
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.team_id == team_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    return workflow


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    team_id: str,
    data: WorkflowCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workflow:
    """Create a new workflow."""

    await get_team_or_404(team_id, db)

    workflow = Workflow(
        team_id=team_id,
        name=data.name,
        description=data.description,
        steps=data.steps,
        status="draft",
        config=data.config,
    )

    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)

    logger.info(f"Created workflow: {workflow.name} ({workflow.id}) for team {team_id}")

    return workflow


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    team_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Workflow]:
    """List workflows for a team."""

    await get_team_or_404(team_id, db)

    query = (
        select(Workflow)
        .where(Workflow.team_id == team_id)
        .order_by(Workflow.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    return list(result.scalars().all())


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    team_id: str,
    workflow_id: str,
    data: WorkflowUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workflow:
    """Update workflow configuration."""

    workflow = await get_workflow_or_404(workflow_id, team_id, db)

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(workflow, field, value)

    await db.flush()
    await db.refresh(workflow)

    logger.info(f"Updated workflow: {workflow.name} ({workflow.id})")

    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    team_id: str,
    workflow_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a workflow."""

    workflow = await get_workflow_or_404(workflow_id, team_id, db)

    await db.delete(workflow)
    await db.flush()

    logger.info(f"Deleted workflow: {workflow.name} ({workflow.id})")
