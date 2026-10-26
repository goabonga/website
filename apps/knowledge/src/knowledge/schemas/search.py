# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Search schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Distance types supported by pgvector
DistanceType = Literal["cosine", "l2", "inner_product"]


class SearchRequest(BaseModel):
    """Schema for search request."""

    query: str = Field(..., min_length=1)
    collection_ids: list[str] | None = Field(
        None,
        description="Collection IDs or slugs to search in. If None, search all.",
    )
    top_k: int = Field(default=10, ge=1, le=100)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    distance_type: DistanceType = Field(
        default="cosine",
        description="Distance metric: cosine (recommended for OpenAI), l2 (euclidean), inner_product",
    )
    filters: dict | None = Field(None, description="Metadata filters")
    include_content: bool = Field(default=True)


class SearchResult(BaseModel):
    """Schema for a single search result."""

    document_id: UUID
    collection_id: UUID
    collection_slug: str
    content: str
    score: float
    metadata: dict


class SearchResponse(BaseModel):
    """Schema for search response."""

    results: list[SearchResult]
    query: str
    total_results: int
