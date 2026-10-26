# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Checkout session schemas."""

from pydantic import BaseModel, Field, HttpUrl

from billing.config import settings


class CheckoutSessionCreate(BaseModel):
    """Schema for creating a checkout session."""

    saas_id: str
    customer_id: str | None = None  # Internal customer ID
    external_id: str | None = None  # SaaS app's user ID (alternative to customer_id)
    price_id: str  # Internal price ID
    success_url: HttpUrl
    cancel_url: HttpUrl
    mode: str = Field("subscription", pattern=r"^(subscription|payment)$")
    quantity: int = Field(1, ge=1, le=settings.checkout_max_quantity)
    trial_period_days: int | None = Field(None, ge=0, le=settings.max_trial_period_days)
    metadata: dict | None = None
    # Optional: for auto-creating customer if not found
    customer_email: str | None = None
    customer_name: str | None = None


class CheckoutSessionResponse(BaseModel):
    """Schema for checkout session response."""

    session_id: str
    url: str
