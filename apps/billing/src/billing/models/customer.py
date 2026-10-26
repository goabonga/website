# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Customer model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billing.models.base import Base

if TYPE_CHECKING:
    from billing.models.saas_app import SaasApp
    from billing.models.subscription import Subscription


class Customer(Base):
    """Customer model.

    Represents a customer in the billing system, linked to a Stripe customer.
    Each customer belongs to a specific SaaS application.
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("saas_app_id", "external_id", name="uq_customer_saas_external"),
        UniqueConstraint("saas_app_id", "stripe_customer_id", name="uq_customer_saas_stripe"),
        Index("ix_customers_saas_app", "saas_app_id"),
        Index("ix_customers_email", "email"),
    )

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    saas_app_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("saas_apps.id", ondelete="CASCADE")
    )

    # External reference (SaaS app's user ID)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Stripe sync
    stripe_customer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Customer details
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Extra data (JSON)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    @property
    def is_deleted(self) -> bool:
        """Check if customer is soft-deleted."""
        return self.deleted_at is not None

    # Relationships
    saas_app: Mapped[SaasApp] = relationship(back_populates="customers")
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
