# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentBase(BaseModel):
    name: str = Field(..., examples=["DevAgent"])
    role: str = Field(..., examples=["developer"])
    description: str | None = ""
    system_prompt: str | None = ""
    model: str = "gpt-4o"
    provider: str = "openai"
    config: dict = Field(default_factory=dict)


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    provider: str | None = None
    config: dict | None = None
    is_active: bool | None = None


class AgentResponse(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
