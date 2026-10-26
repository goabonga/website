# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Billing price model."""

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
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billing.config import settings
from billing.models.base import Base

if TYPE_CHECKING:
    from billing.models.product import BillingProduct


class BillingType(StrEnum):
    """Type of billing for a price."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"


class UsageType(StrEnum):
    """Type of usage tracking for a price."""

    LICENSED = "licensed"  # Fixed quantity
    METERED = "metered"  # Usage-based


class BillingPrice(Base):
    """Billing price model.

    Represents a price point for a product in Stripe.
    Supports one-time, recurring, and usage-based pricing.
    """

    __tablename__ = "billing_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "stripe_price_id", name="uq_price_product_stripe"),
        Index("ix_prices_product", "product_id"),
    )

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    product_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("billing_products.id", ondelete="CASCADE")
    )

    # Stripe sync
    stripe_price_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Price details
    nickname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default=lambda: settings.default_currency)
    unit_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # In cents

    # Billing configuration
    billing_type: Mapped[BillingType] = mapped_column(
        SAEnum(
            BillingType,
            values_callable=lambda enum: [e.value for e in enum],
            name="billingtype",
        ),
        default=BillingType.RECURRING,
    )
    recurring_interval: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # day, week, month, year
    recurring_interval_count: Mapped[int] = mapped_column(Integer, default=1)

    # Usage-based pricing
    usage_type: Mapped[UsageType] = mapped_column(
        SAEnum(
            UsageType,
            values_callable=lambda enum: [e.value for e in enum],
            name="usagetype",
        ),
        default=UsageType.LICENSED,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    product: Mapped[BillingProduct] = relationship(back_populates="prices")
