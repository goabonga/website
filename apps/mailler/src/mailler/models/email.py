# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email and ProviderStats models for Mailler."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mailler.models.base import Base


class EmailStatus(StrEnum):
    """Email delivery status."""

    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    FAILED = "failed"


class Email(Base):
    """Individual email record."""

    __tablename__ = "emails"
    # The limits of the clients count their recent emails
    __table_args__ = (
        Index("ix_emails_client_id_created_at", "client_id", "created_at"),
        # One email per idempotency key and client (emails without a key are not constrained)
        UniqueConstraint("client_id", "idempotency_key", name="uq_emails_client_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Recipient info
    to_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    to_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Sender info
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Content
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmailStatus.PENDING.value, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Scheduling
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Timestamps
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Metadata (custom headers, tags, etc.)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Request context
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # Key sent by the client to make a request safe to repeat
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Celery task tracking
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        """String representation."""
        return f"<Email(id={self.id}, to={self.to_email}, status={self.status})>"


class ProviderStats(Base):
    """Daily statistics per provider."""

    __tablename__ = "provider_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Counts
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bounced_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("date", "provider", name="uq_provider_stats_date_provider"),)

    def __repr__(self) -> str:
        """String representation."""
        return f"<ProviderStats(date={self.date}, provider={self.provider})>"
