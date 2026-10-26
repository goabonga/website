# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Conversation management routes (multi-agent coordination)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import Agent, Conversation, ConversationParticipant
from team.schemas import ConversationCreate, ConversationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/conversations", tags=["Team - Conversations"])


async def get_conversation_or_404(conversation_id: str, db: AsyncSession) -> Conversation:
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


async def get_agent_or_404(agent_id: str, db: AsyncSession) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Conversation:
    """Create a new multi-agent conversation."""

    conversation = Conversation(
        slug=data.slug,
        title=data.title,
        type=data.type,
        status="active",
        extra=data.extra,
    )

    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)

    logger.info(f"Created conversation: {conversation.slug} ({conversation.id})")

    return conversation


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Conversation]:
    """List all conversations."""

    query = (
        select(Conversation).order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
    )

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Conversation:
    """Get conversation by ID."""

    return await get_conversation_or_404(conversation_id, db)


@router.post("/{conversation_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_agent_to_conversation(
    conversation_id: str,
    agent_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Attach an agent to a conversation."""

    conversation = await get_conversation_or_404(conversation_id, db)
    agent = await get_agent_or_404(agent_id, db)

    participant = ConversationParticipant(
        conversation_id=conversation.id,
        agent_id=agent.id,
        role="member",
    )

    db.add(participant)
    await db.flush()

    logger.info(f"Agent {agent.name} joined conversation {conversation.slug}")


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a conversation."""

    conversation = await get_conversation_or_404(conversation_id, db)

    await db.delete(conversation)
    await db.flush()

    logger.info(f"Deleted conversation: {conversation.slug} ({conversation.id})")
