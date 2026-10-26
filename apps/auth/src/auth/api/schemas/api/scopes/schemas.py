# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for scopes API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateScopeRequest(BaseModel):
    """Request body for creating a scope."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    resource: str = Field(..., min_length=1, max_length=50)
    action: str = Field(..., min_length=1, max_length=50)
    category: str = Field(default="admin", max_length=50)


class UpdateScopeRequest(BaseModel):
    """Request body for partially updating a scope."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    resource: str | None = Field(None, min_length=1, max_length=50)
    action: str | None = Field(None, min_length=1, max_length=50)
    category: str | None = Field(None, max_length=50)


class ScopeResponse(BaseModel):
    """Response for a single scope."""

    id: uuid.UUID
    name: str
    description: str | None = None
    resource: str
    action: str
    category: str
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
