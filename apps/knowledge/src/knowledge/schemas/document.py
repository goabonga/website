# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Document schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    """Schema for creating a single document."""

    content: str = Field(..., min_length=1)
    metadata: dict = Field(default_factory=dict)
    source_type: str | None = Field(None, max_length=50)
    source_ref: str | None = Field(None, max_length=500)


class DocumentsCreate(BaseModel):
    """Schema for creating multiple documents."""

    documents: list[DocumentCreate] = Field(..., min_length=1, max_length=100)


class DocumentResponse(BaseModel):
    """Schema for document response."""

    id: UUID
    collection_id: UUID
    content: str
    metadata: dict = Field(validation_alias="doc_metadata")
    source_type: str | None
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentWithScore(BaseModel):
    """Schema for document with similarity score."""

    id: UUID
    collection_id: UUID
    content: str
    metadata: dict = Field(validation_alias="doc_metadata")
    source_type: str | None
    source_ref: str | None
    score: float
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
