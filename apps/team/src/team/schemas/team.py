# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TeamBase(BaseModel):
    name: str = Field(..., examples=["Engineering"])
    slug: str = Field(..., examples=["engineering"])
    description: str | None = ""
    config: dict = Field(default_factory=dict)


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    is_active: bool | None = None


class TeamResponse(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
