# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Subscription model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billing.models.base import Base

if TYPE_CHECKING:
    from billing.models.customer import Customer
    from billing.models.price import BillingPrice
    from billing.models.usage_event import UsageEvent


class SubscriptionStatus(StrEnum):
    """Subscription status values from Stripe."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    UNPAID = "unpaid"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    PAUSED = "paused"


class Subscription(Base):
    """Subscription model.

    Represents a customer's subscription to a product/price in Stripe.
    Tracks subscription status and billing periods.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "stripe_subscription_id",
            name="uq_subscription_customer_stripe",
        ),
        Index("ix_subscriptions_customer", "customer_id"),
        Index("ix_subscriptions_status", "status"),
    )

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    customer_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE")
    )
    price_id: Mapped[str | None] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("billing_prices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Stripe sync
    stripe_subscription_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    stripe_subscription_item_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # For metered usage

    # Subscription details
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(
            SubscriptionStatus,
            values_callable=lambda enum: [e.value for e in enum],
            name="subscriptionstatus",
        ),
        default=SubscriptionStatus.ACTIVE,
    )

    # Billing period
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Cancellation
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Extra data (JSON)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    customer: Mapped[Customer] = relationship(back_populates="subscriptions")
    price: Mapped[BillingPrice | None] = relationship()
    usage_events: Mapped[list[UsageEvent]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
