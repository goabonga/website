# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Search routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import Auth
from knowledge.database import get_db
from knowledge.schemas.search import SearchRequest, SearchResponse
from knowledge.services.search import SearchService

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search across collections.

    Performs semantic similarity search using vector embeddings.
    """
    auth.require_scope("collections:search")

    service = SearchService(db)
    return await service.search(auth.tenant_id, request)


@router.post("/collections/{collection_id}", response_model=SearchResponse)
async def search_collection(
    collection_id: str,
    request: SearchRequest,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search within a specific collection."""
    auth.require_scope("collections:search")

    # Override collection_ids with the specified collection
    request.collection_ids = [collection_id]

    service = SearchService(db)
    return await service.search(auth.tenant_id, request)
