# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for roles API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateRoleRequest(BaseModel):
    """Request body for creating a role."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    scope_ids: list[uuid.UUID] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    """Request body for partially updating a role."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    scope_ids: list[uuid.UUID] | None = None


class AssignRoleRequest(BaseModel):
    """Request body for assigning a role to a user."""

    user_id: uuid.UUID


class RoleResponse(BaseModel):
    """Response for a single role."""

    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    scopes: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SeedRolesResponse(BaseModel):
    """Response for the seed-default-roles endpoint."""

    message: str
    created_roles: list[str]
