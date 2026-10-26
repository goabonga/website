# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Workspace deletion request model for email confirmation."""

import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from knowledge.models.base import Base

if TYPE_CHECKING:
    from knowledge.models.organization import Organization


class DeletionRequestStatus(StrEnum):
    """Status of a workspace deletion request."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SCHEDULED = "scheduled"  # Deletion scheduled for end of billing period
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class WorkspaceDeletionRequest(Base):
    """Request to delete a workspace, requires email confirmation."""

    __tablename__ = "workspace_deletion_requests"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[DeletionRequestStatus] = mapped_column(
        SQLEnum(
            DeletionRequestStatus,
            name="deletionrequeststatus",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=DeletionRequestStatus.PENDING,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    scheduled_deletion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When set, deletion is scheduled for this date (end of billing period)",
    )
    subscription_cancelled: Mapped[bool] = mapped_column(
        default=False,
        doc="True if the billing subscription was cancelled as part of deletion",
    )
    cancel_token: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
        doc="Token used to cancel the scheduled deletion via email link",
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the reminder email was sent (1 day before deletion)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        foreign_keys=[organization_id],
    )

    def __repr__(self) -> str:
        return f"<WorkspaceDeletionRequest {self.organization_id} ({self.status.value})>"

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)

    @classmethod
    def default_expiry(cls) -> datetime:
        """Get default expiry time (24 hours from now)."""
        return datetime.now(UTC) + timedelta(hours=24)

    @property
    def is_pending(self) -> bool:
        """Check if request is still pending."""
        return self.status == DeletionRequestStatus.PENDING

    @property
    def is_expired(self) -> bool:
        """Check if request has expired."""
        if self.status == DeletionRequestStatus.EXPIRED:
            return True
        return self.expires_at < datetime.now(UTC)

    @property
    def is_valid(self) -> bool:
        """Check if request can be confirmed."""
        return self.is_pending and not self.is_expired

    @property
    def is_scheduled(self) -> bool:
        """Check if deletion is scheduled for later."""
        return self.status == DeletionRequestStatus.SCHEDULED

    @property
    def is_ready_to_delete(self) -> bool:
        """Check if scheduled deletion is ready to execute."""
        if not self.is_scheduled or not self.scheduled_deletion_at:
            return False
        return datetime.now(UTC) >= self.scheduled_deletion_at

    def confirm(self) -> None:
        """Mark request as confirmed (immediate deletion)."""
        self.status = DeletionRequestStatus.CONFIRMED
        self.confirmed_at = datetime.now(UTC)

    def schedule(self, deletion_date: datetime, subscription_cancelled: bool = True) -> None:
        """Schedule deletion for a future date (end of billing period)."""
        self.status = DeletionRequestStatus.SCHEDULED
        self.confirmed_at = datetime.now(UTC)
        self.scheduled_deletion_at = deletion_date
        self.subscription_cancelled = subscription_cancelled
        # Generate a cancel token for allowing user to abort the deletion
        self.cancel_token = self.generate_token()

    @property
    def needs_reminder(self) -> bool:
        """Check if reminder email should be sent (1 day before deletion)."""
        if not self.is_scheduled or not self.scheduled_deletion_at:
            return False
        if self.reminder_sent_at is not None:
            return False
        # Send reminder 1 day before deletion
        reminder_threshold = self.scheduled_deletion_at - timedelta(days=1)
        return datetime.now(UTC) >= reminder_threshold

    def mark_reminder_sent(self) -> None:
        """Mark that the reminder email has been sent."""
        self.reminder_sent_at = datetime.now(UTC)

    def execute_scheduled(self) -> None:
        """Mark scheduled deletion as executed."""
        self.status = DeletionRequestStatus.CONFIRMED

    def cancel(self) -> None:
        """Cancel the request."""
        self.status = DeletionRequestStatus.CANCELLED

    def mark_expired(self) -> None:
        """Mark request as expired."""
        self.status = DeletionRequestStatus.EXPIRED
