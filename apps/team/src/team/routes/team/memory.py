# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Memory management routes (shared knowledge / RAG)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import MemoryEntry, Team
from team.schemas import MemoryEntryCreate, MemoryEntryResponse, MemoryEntryUpdate
from team.services.embeddings import generate_embedding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/{team_id}/memory", tags=["Platform - Memory"])


async def get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    return team


async def _get_entry_or_404(team_id: str, entry_id: str, db: AsyncSession) -> MemoryEntry:
    result = await db.execute(
        select(MemoryEntry).where(MemoryEntry.id == entry_id, MemoryEntry.team_id == team_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found",
        )
    return entry


@router.get("", response_model=list[MemoryEntryResponse])
async def list_memory(
    team_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[MemoryEntry]:
    """Access shared memory for a team."""

    await get_team_or_404(team_id, db)

    query = (
        select(MemoryEntry)
        .where(MemoryEntry.team_id == team_id)
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=MemoryEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory_entry(
    team_id: str,
    data: MemoryEntryCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemoryEntry:
    """Create a memory entry for a team."""

    await get_team_or_404(team_id, db)

    embedding = await generate_embedding(data.content)

    entry = MemoryEntry(
        team_id=team_id,
        agent_id=data.agent_id,
        conversation_id=data.conversation_id,
        content=data.content,
        extra=data.extra,
        embedding=embedding,
    )

    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    logger.info(f"Created memory entry ({entry.id}) for team {team_id}")

    return entry


@router.patch("/{entry_id}", response_model=MemoryEntryResponse)
async def update_memory_entry(
    team_id: str,
    entry_id: str,
    data: MemoryEntryUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemoryEntry:
    """Update a memory entry's content and/or metadata."""

    await get_team_or_404(team_id, db)
    entry = await _get_entry_or_404(team_id, entry_id, db)

    if data.content is not None:
        entry.content = data.content
        entry.embedding = await generate_embedding(data.content)
    if data.extra is not None:
        entry.extra = data.extra

    await db.flush()
    await db.refresh(entry)

    logger.info(f"Updated memory entry ({entry_id}) for team {team_id}")
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_entry(
    team_id: str,
    entry_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a memory entry."""

    await get_team_or_404(team_id, db)
    entry = await _get_entry_or_404(team_id, entry_id, db)

    await db.delete(entry)
    await db.flush()

    logger.info(f"Deleted memory entry ({entry_id}) for team {team_id}")
