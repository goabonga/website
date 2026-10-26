# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from team.models.base import Base


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    role: Mapped[str] = mapped_column(
        String(50), default="member"
    )  # member | coordinator | observer

    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="participants")
