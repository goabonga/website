# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowBase(BaseModel):
    name: str = Field(..., examples=["Deploy Pipeline"])
    description: str | None = ""
    steps: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: dict | None = None
    status: str | None = None
    config: dict | None = None


class WorkflowResponse(WorkflowBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
