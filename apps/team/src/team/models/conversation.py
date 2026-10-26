# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from team.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # general / task-123
    title: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(
        String(50), default="general"
    )  # general | task | incident | workflow
    status: Mapped[str] = mapped_column(String(50), default="active")

    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    team = relationship("Team")
    messages = relationship("Message", back_populates="conversation", cascade="all,delete")
    participants = relationship(
        "ConversationParticipant", back_populates="conversation", cascade="all,delete"
    )
