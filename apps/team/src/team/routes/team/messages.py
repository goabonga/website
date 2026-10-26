# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Message routes (agent-to-agent communication)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import Agent, Conversation, Message
from team.schemas import MessageCreate, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/conversations", tags=["Team - Messages"])


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


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def post_message(
    conversation_id: str,
    data: MessageCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Message:
    """Post a message inside a conversation."""

    conversation = await get_conversation_or_404(conversation_id, db)
    await get_agent_or_404(str(data.agent_id), db)

    message = Message(
        conversation_id=conversation.id,
        agent_id=data.agent_id,
        type=data.type,
        content=data.content,
        text=data.text,
        visibility=data.visibility,
    )

    db.add(message)
    await db.flush()
    await db.refresh(message)

    logger.info(f"Message posted in conversation {conversation.slug}")

    return message


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Message]:
    """List messages for a conversation."""

    await get_conversation_or_404(conversation_id, db)

    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    return list(result.scalars().all())
