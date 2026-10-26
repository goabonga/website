# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Usage event schemas for task execution reporting."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsageReport(BaseModel):
    """Schema for reporting a task execution event."""

    agent_id: UUID
    task_id: UUID | None = None
    action: str = Field(..., max_length=100, examples=["task.completed"])
    details: dict = Field(default_factory=dict)
    timestamp: datetime | None = None


class UsageBatchReport(BaseModel):
    """Schema for batch reporting agent activity."""

    events: list[UsageReport] = Field(..., min_length=1, max_length=100)


class UsageEventResponse(BaseModel):
    """Schema for usage event response."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    team_id: UUID
    agent_id: UUID
    task_id: UUID | None
    action: str = Field(validation_alias="event_type")
    details: dict
    timestamp: datetime = Field(validation_alias="created_at")
    created_at: datetime
