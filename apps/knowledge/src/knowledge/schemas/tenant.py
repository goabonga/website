# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from knowledge.models.enums import PlanType


class TenantCreate(BaseModel):
    """Schema for creating a tenant."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class TenantResponse(BaseModel):
    """Schema for tenant response."""

    id: UUID
    name: str
    slug: str
    plan: PlanType
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
