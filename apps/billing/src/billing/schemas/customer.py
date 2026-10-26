# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Customer schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CustomerCreate(BaseModel):
    """Schema for creating a customer."""

    external_id: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    name: str | None = Field(None, max_length=255)
    extra_data: dict | None = None


class CustomerUpdate(BaseModel):
    """Schema for updating a customer."""

    email: EmailStr | None = None
    name: str | None = Field(None, max_length=255)
    extra_data: dict | None = None


class CustomerResponse(BaseModel):
    """Schema for customer response."""

    id: str
    saas_app_id: str
    external_id: str
    stripe_customer_id: str
    email: str
    name: str | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerPortalResponse(BaseModel):
    """Schema for customer portal session response."""

    url: str
