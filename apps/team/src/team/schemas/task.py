# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    title: str = Field(..., examples=["Review PR #42"])
    description: str | None = ""
    priority: int = 0
    input_data: dict = Field(default_factory=dict)


class TaskCreate(TaskBase):
    workflow_id: UUID | None = None
    agent_id: UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    agent_id: UUID | None = None
    input_data: dict | None = None
    output_data: dict | None = None


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    workflow_id: UUID | None
    agent_id: UUID | None
    status: str
    output_data: dict
    created_at: datetime
    updated_at: datetime
