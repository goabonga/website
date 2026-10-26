# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Price schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from billing.config import settings
from billing.models.price import BillingType, UsageType


class PriceCreate(BaseModel):
    """Schema for creating a price."""

    nickname: str | None = Field(None, max_length=255)
    currency: str = Field(
        default_factory=lambda: settings.default_currency, min_length=3, max_length=3
    )
    unit_amount: int | None = Field(None, ge=0)  # In cents
    billing_type: BillingType = BillingType.RECURRING
    recurring_interval: str | None = Field(
        None, pattern=r"^(day|week|month|year)$"
    )  # day, week, month, year
    recurring_interval_count: int = Field(1, ge=1, le=365)
    usage_type: UsageType = UsageType.LICENSED


class PriceUpdate(BaseModel):
    """Schema for updating a price (limited fields - Stripe prices are mostly immutable)."""

    nickname: str | None = None
    is_active: bool | None = None


class PriceResponse(BaseModel):
    """Schema for price response."""

    id: str
    product_id: str
    stripe_price_id: str
    nickname: str | None
    currency: str
    unit_amount: int | None
    billing_type: BillingType
    recurring_interval: str | None
    recurring_interval_count: int
    usage_type: UsageType
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
