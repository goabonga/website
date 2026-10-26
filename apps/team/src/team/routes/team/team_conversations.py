# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Team-scoped conversation routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import Conversation, Team
from team.schemas import ConversationResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/platform/{team_id}/conversations", tags=["Platform - Team Conversations"]
)


async def _get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    return team


@router.get("", response_model=list[ConversationResponse])
async def list_team_conversations(
    team_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Conversation]:
    """List conversations for a team."""
    await _get_team_or_404(team_id, db)

    query = (
        select(Conversation)
        .where(Conversation.team_id == team_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/count")
async def count_team_conversations(
    team_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get conversation count for a team."""
    await _get_team_or_404(team_id, db)

    result = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.team_id == team_id)
    )
    total = result.scalar_one()
    return {"count": total}
