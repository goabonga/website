# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    agent_id: UUID
    type: str = "message"
    content: dict = Field(default_factory=dict)
    text: str = ""
    visibility: str = "public"


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    agent_id: UUID | None
    type: str
    content: dict
    text: str
    visibility: str
    created_at: datetime
