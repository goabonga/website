# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Plan schemas for public API."""

from datetime import datetime

from pydantic import BaseModel, Field

from billing.models.price import BillingType


class PlanFeature(BaseModel):
    """A feature included in a plan."""

    label: str
    highlight: bool = False
    disabled: bool = False


# Quota limits of a plan: any keys defined by the SaaS application (for example
# "max_seats"), each with an integer value. The platform does not interpret them.
PlanLimits = dict[str, int]


class PlanPrice(BaseModel):
    """Price information for a plan."""

    id: str
    currency: str
    unit_amount: int | None = Field(None, description="Price in cents")
    billing_type: BillingType
    interval: str | None = Field(None, description="Billing interval (month, year)")
    interval_count: int = 1

    model_config = {"from_attributes": True}


class PlanResponse(BaseModel):
    """A billing plan (product + prices)."""

    id: str
    slug: str = Field(..., description="Plan identifier (e.g., 'free', 'starter', 'pro')")
    name: str
    description: str | None = None
    features: list[PlanFeature] = Field(default_factory=list)
    limits: PlanLimits | None = None
    prices: list[PlanPrice] = Field(default_factory=list)
    is_recommended: bool = False
    sort_order: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class PlansResponse(BaseModel):
    """List of plans for a SaaS app."""

    app_slug: str
    plans: list[PlanResponse]
