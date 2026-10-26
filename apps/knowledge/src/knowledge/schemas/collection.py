# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collection schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    """Schema for creating a collection."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = Field(None, max_length=1000)
    embedding_model: str = Field(default="text-embedding-3-small", max_length=100)
    dimension: int = Field(default=1536, ge=1, le=4096)
    metadata_schema: dict | None = None


class CollectionUpdate(BaseModel):
    """Schema for updating a collection."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    metadata_schema: dict | None = None


class CollectionResponse(BaseModel):
    """Schema for collection response."""

    id: UUID
    tenant_id: UUID | None
    name: str
    slug: str
    description: str | None
    embedding_model: str
    dimension: int
    metadata_schema: dict | None
    document_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
