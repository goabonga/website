# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationBase(BaseModel):
    slug: str = Field(..., examples=["general"])
    title: str
    type: str = "general"
    extra: dict = Field(default_factory=dict)


class ConversationCreate(ConversationBase):
    pass


class ConversationUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    extra: dict | None = None


class ConversationResponse(ConversationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID | None = None
    status: str
    created_at: datetime
    updated_at: datetime
