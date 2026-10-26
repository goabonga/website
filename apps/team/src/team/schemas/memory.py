# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MemoryEntryCreate(BaseModel):
    content: str
    agent_id: UUID | None = None
    conversation_id: UUID | None = None
    extra: dict = Field(default_factory=dict)


class MemoryEntryUpdate(BaseModel):
    content: str | None = None
    extra: dict | None = None


class MemoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID | None
    agent_id: UUID | None
    conversation_id: UUID | None
    content: str
    extra: dict
    created_at: datetime
