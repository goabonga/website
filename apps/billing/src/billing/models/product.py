# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Billing product model."""

from __future__ import annotations

from datetime import datetime
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billing.models.base import Base

if TYPE_CHECKING:
    from billing.models.price import BillingPrice
    from billing.models.saas_app import SaasApp


class BillingProduct(Base):
    """Billing product model.

    Represents a product in Stripe, linked to a specific SaaS application.
    Products can have multiple prices (monthly, yearly, etc.).
    """

    __tablename__ = "billing_products"
    __table_args__ = (
        UniqueConstraint("saas_app_id", "stripe_product_id", name="uq_product_saas_stripe"),
        UniqueConstraint("saas_app_id", "slug", name="uq_product_saas_slug"),
        Index("ix_products_saas_app", "saas_app_id"),
    )

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    saas_app_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("saas_apps.id", ondelete="CASCADE")
    )

    # Stripe sync
    stripe_product_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Plan identifier, unique inside the SaaS application (e.g. "free", "pro")
    slug: Mapped[str] = mapped_column(String(100), nullable=False)

    # Product details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Extra data (synced from Stripe metadata)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    saas_app: Mapped[SaasApp] = relationship(back_populates="products")
    prices: Mapped[list[BillingPrice]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
