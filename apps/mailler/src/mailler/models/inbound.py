# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Inbound email models for Mailler."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mailler.models.base import Base


class InboundStatus(StrEnum):
    """Inbound email processing status."""

    RECEIVED = "received"
    FORWARDED = "forwarded"
    FAILED = "failed"


class InboundEmail(Base):
    """Inbound email received via IMAP."""

    __tablename__ = "inbound_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Email identifiers
    message_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Sender
    from_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Recipients (stored as JSONB lists of {Address, Name} objects)
    to_emails: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    cc_emails: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    reply_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Content
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Headers (full email headers as dict)
    headers: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Metadata
    sent_at_date: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spam_score: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # Processing status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InboundStatus.RECEIVED.value, index=True
    )
    webhook_response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # IMAP reference
    imap_uid: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    forwarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    attachments: Mapped[list["InboundAttachment"]] = relationship(
        back_populates="inbound_email", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<InboundEmail(id={self.id}, from={self.from_email}, subject={self.subject})>"


class InboundAttachment(Base):
    """Attachment for an inbound email."""

    __tablename__ = "inbound_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Parent email
    inbound_email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inbound_emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # File metadata
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False)
    content_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # Download token (for Brevo-compatible download endpoint)
    download_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4, index=True
    )

    # Storage
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    inbound_email: Mapped["InboundEmail"] = relationship(back_populates="attachments")

    def __repr__(self) -> str:
        """String representation."""
        return f"<InboundAttachment(id={self.id}, filename={self.filename})>"
