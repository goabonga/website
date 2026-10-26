# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Subscription schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from billing.config import settings
from billing.models.subscription import SubscriptionStatus


class ProrationBehavior(StrEnum):
    """Proration behavior options for subscription changes."""

    CREATE_PRORATIONS = "create_prorations"  # Credit applied to next invoice (default)
    ALWAYS_INVOICE = "always_invoice"  # Invoice immediately with proration
    NONE = "none"  # No proration (not recommended for upgrades)


class SubscriptionCreate(BaseModel):
    """Schema for creating a subscription."""

    price_id: str  # Internal price ID
    trial_period_days: int | None = Field(None, ge=0, le=settings.max_trial_period_days)
    extra_data: dict | None = None


class SubscriptionUpdate(BaseModel):
    """Schema for updating a subscription."""

    cancel_at_period_end: bool | None = None
    extra_data: dict | None = None


class SubscriptionUpgradeRequest(BaseModel):
    """Schema for upgrading a subscription to a new plan."""

    new_price_id: str = Field(..., description="The internal price ID to upgrade to")
    proration_behavior: ProrationBehavior = Field(
        default=ProrationBehavior.CREATE_PRORATIONS,
        description="How to handle proration: create_prorations (credit on next invoice), "
        "always_invoice (charge immediately), none (no proration)",
    )


class ProrationLineItem(BaseModel):
    """A single line item in the proration preview."""

    description: str
    amount: int  # In minor units (negative = credit, positive = charge)
    currency: str = Field(default_factory=lambda: settings.default_currency)

    @property
    def display_amount(self) -> str:
        """Get display-friendly amount, followed by the currency code."""
        major = abs(self.amount) // 100
        minor = abs(self.amount) % 100
        sign = "-" if self.amount < 0 else ""
        code = self.currency.upper()
        if minor == 0:
            return f"{sign}{major} {code}"
        return f"{sign}{major}.{minor:02d} {code}"


class SubscriptionUpgradePreview(BaseModel):
    """Preview of what a subscription upgrade will cost."""

    current_plan_name: str
    new_plan_name: str
    current_price_amount: int  # Monthly price in cents
    new_price_amount: int  # Monthly price in cents
    proration_date: datetime
    period_end: datetime
    line_items: list[ProrationLineItem]
    subtotal: int  # In cents
    total: int  # Amount due now (in cents)
    credit_applied: int  # Credit from current plan (in cents, always positive)
    currency: str = Field(default_factory=lambda: settings.default_currency)

    @property
    def display_total(self) -> str:
        """Get display-friendly total amount, followed by the currency code."""
        major = abs(self.total) // 100
        minor = abs(self.total) % 100
        sign = "-" if self.total < 0 else ""
        code = self.currency.upper()
        if minor == 0:
            return f"{sign}{major} {code}"
        return f"{sign}{major}.{minor:02d} {code}"


class SubscriptionUpgradeResponse(BaseModel):
    """Response after upgrading a subscription."""

    subscription: "SubscriptionResponse"
    proration_applied: bool
    amount_due: int  # In cents
    invoice_id: str | None = None


class SubscriptionResponse(BaseModel):
    """Schema for subscription response."""

    id: str
    customer_id: str
    price_id: str | None
    stripe_subscription_id: str
    stripe_subscription_item_id: str | None
    status: SubscriptionStatus
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Update forward reference
SubscriptionUpgradeResponse.model_rebuild()
