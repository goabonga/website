# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email campaign and send tracking models."""

import uuid as uuid_lib
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mailler.models.base import Base


class CampaignStatus(StrEnum):
    """Status of an email campaign."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class EmailSendStatus(StrEnum):
    """Status of an individual email send."""

    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    FAILED = "failed"


class EmailCampaign(Base):
    """Email campaign for sending to contacts.

    A campaign uses a template and targets a contact group or list of contacts.
    Tracks sending progress and statistics.
    """

    __tablename__ = "email_campaigns"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    # Owner: campaigns are private to the client that created them
    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    template_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("email_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contact_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CampaignStatus.DRAFT.value,
        index=True,
    )
    # Scheduling
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Statistics (updated during/after sending)
    total_recipients: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    sent_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    delivered_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    opened_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    clicked_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    bounced_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    complained_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    # Email settings override (optional)
    from_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    from_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    reply_to: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # Email provider (brevo, sendgrid, ses, protonmail)
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    # Subject line override (uses template subject if not set)
    subject_override: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    # Extra metadata and config
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
    )
    # Celery task ID for tracking
    task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    template: Mapped["EmailTemplate"] = relationship(
        "EmailTemplate",
        lazy="joined",
    )
    group: Mapped["ContactGroup"] = relationship(
        "ContactGroup",
        lazy="joined",
    )
    sends: Mapped[list["EmailSend"]] = relationship(
        "EmailSend",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    @property
    def progress_percent(self) -> float:
        """Calculate sending progress as percentage."""
        if self.total_recipients == 0:
            return 0.0
        return round((self.sent_count / self.total_recipients) * 100, 1)

    @property
    def open_rate(self) -> float:
        """Calculate open rate as percentage."""
        if self.delivered_count == 0:
            return 0.0
        return round((self.opened_count / self.delivered_count) * 100, 1)

    @property
    def click_rate(self) -> float:
        """Calculate click rate as percentage."""
        if self.delivered_count == 0:
            return 0.0
        return round((self.clicked_count / self.delivered_count) * 100, 1)

    @property
    def bounce_rate(self) -> float:
        """Calculate bounce rate as percentage."""
        if self.sent_count == 0:
            return 0.0
        return round((self.bounced_count / self.sent_count) * 100, 1)

    @property
    def complaint_rate(self) -> float:
        """Calculate complaint rate as percentage."""
        if self.delivered_count == 0:
            return 0.0
        return round((self.complained_count / self.delivered_count) * 100, 2)

    def __repr__(self) -> str:
        return f"<EmailCampaign(id={self.id}, name='{self.name}', status='{self.status}')>"


class EmailSend(Base):
    """Individual email send record.

    Tracks the status and events for each email sent in a campaign.
    """

    __tablename__ = "email_sends"

    id: Mapped[uuid_lib.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_lib.uuid4,
    )
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("email_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[uuid_lib.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Snapshot of recipient info (in case contact is deleted)
    recipient_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    recipient_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EmailSendStatus.PENDING.value,
        index=True,
    )
    # Timestamps for events
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    bounced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Error tracking
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    smtp_response: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    # Message ID for tracking (from SMTP server)
    message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    # Extra data (click URLs, etc.)
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    campaign: Mapped[EmailCampaign] = relationship(
        "EmailCampaign",
        back_populates="sends",
        lazy="joined",
    )
    contact: Mapped["Contact"] = relationship(
        "Contact",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<EmailSend(id={self.id}, email='{self.recipient_email}', status='{self.status}')>"


# Import for type hints (avoid circular imports)
from mailler.models.contact import Contact, ContactGroup  # noqa: E402
from mailler.models.template import EmailTemplate  # noqa: E402
