# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Usage event model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billing.models.base import Base

if TYPE_CHECKING:
    from billing.models.subscription import Subscription


class UsageEventStatus(StrEnum):
    """Status of a usage event."""

    PENDING = "pending"
    REPORTED = "reported"
    FAILED = "failed"


class UsageEvent(Base):
    """Usage event model.

    Represents a usage event for metered billing.
    Events are batched and reported to Stripe periodically.
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("saas_app_id", "idempotency_key", name="uq_usage_saas_idempotency"),
        Index("ix_usage_events_saas_app", "saas_app_id"),
        Index("ix_usage_events_subscription", "subscription_id"),
        Index("ix_usage_events_status", "status"),
        Index("ix_usage_events_timestamp", "timestamp"),
        Index(
            "ix_usage_events_pending",
            "status",
            "created_at",
            postgresql_where="status = 'pending'",
        ),
    )

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    saas_app_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("saas_apps.id", ondelete="CASCADE")
    )
    subscription_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("subscriptions.id", ondelete="CASCADE")
    )

    # Usage details
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Idempotency key (prevents duplicate reporting), unique per SaaS application
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Stripe reporting
    status: Mapped[UsageEventStatus] = mapped_column(
        SAEnum(
            UsageEventStatus,
            values_callable=lambda enum: [e.value for e in enum],
            name="usageeventstatus",
        ),
        default=UsageEventStatus.PENDING,
    )
    stripe_usage_record_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Extra data for debugging
    action: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # e.g., "api_call", "message_sent"
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    subscription: Mapped[Subscription] = relationship(back_populates="usage_events")
