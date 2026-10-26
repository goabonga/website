# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for API validation."""

from knowledge.schemas.collection import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
)
from knowledge.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentsCreate,
)
from knowledge.schemas.search import SearchRequest, SearchResponse, SearchResult
from knowledge.schemas.tenant import TenantCreate, TenantResponse

__all__ = [
    "CollectionCreate",
    "CollectionResponse",
    "CollectionUpdate",
    "DocumentCreate",
    "DocumentResponse",
    "DocumentsCreate",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "TenantCreate",
    "TenantResponse",
]
