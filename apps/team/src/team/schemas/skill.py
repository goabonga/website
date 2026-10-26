# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for Agent Skills (agentskills.io spec)."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        examples=["code-review"],
        description="Lowercase alphanumeric name with hyphens (1-64 chars)",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        examples=["Review code changes for quality, security, and best practices."],
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Markdown instructions (skill body)",
    )
    license: str = Field(default="", max_length=120)
    compatibility: str = Field(default="", max_length=500)
    metadata: dict = Field(default_factory=dict, alias="metadata")
    allowed_tools: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                "name must contain only lowercase letters, numbers, and hyphens "
                "(e.g. 'code-review'). Must not start/end with a hyphen."
            )
        return v


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, min_length=1, max_length=1024)
    content: str | None = Field(default=None, min_length=1)
    license: str | None = Field(default=None, max_length=120)
    compatibility: str | None = Field(default=None, max_length=500)
    metadata: dict | None = Field(default=None, alias="metadata")
    allowed_tools: list[str] | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None and not _NAME_RE.match(v):
            raise ValueError("name must contain only lowercase letters, numbers, and hyphens")
        return v


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    team_id: UUID
    name: str
    description: str
    content: str
    license: str
    compatibility: str
    metadata: dict = Field(validation_alias="metadata_")
    allowed_tools: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SkillSummaryResponse(BaseModel):
    """Lightweight response for listing skills (progressive disclosure)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    name: str
    description: str
    is_active: bool
    created_at: datetime
