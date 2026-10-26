# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Analytics event model."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analytics.models.base import Base


class Event(Base):
    """Analytics event tracking."""

    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Session reference
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analytics_sessions.id", ondelete="CASCADE"),
        index=True,
    )

    # Event information
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    event_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Page context
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )

    # Relationships
    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="events",
    )

    __table_args__ = (Index("ix_analytics_events_type_timestamp", "event_type", "timestamp"),)

    def __repr__(self) -> str:
        return f"<Event {self.event_type} at {self.timestamp}>"


# Import Session for relationship (avoid circular import)
from analytics.models.session import Session  # noqa: E402, F401
