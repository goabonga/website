# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for search routes (knowledge/routes/search.py)."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from knowledge.schemas.search import SearchResponse, SearchResult


def _make_search_response(results=None):
    """Create a mock SearchResponse."""
    if results is None:
        results = [
            SearchResult(
                document_id=uuid4(),
                collection_id=uuid4(),
                collection_slug="test-collection",
                content="Test document content",
                score=0.95,
                metadata={"key": "value"},
            )
        ]
    return SearchResponse(
        results=results,
        query="test query",
        total_results=len(results),
    )


# ============================================================
# POST /search
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.search.SearchService")
async def test_search(MockService, client: AsyncClient):
    """Test search across collections."""
    instance = MockService.return_value
    instance.search = AsyncMock(return_value=_make_search_response())

    response = await client.post(
        "/api/v1/search",
        json={"query": "test query"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_results"] == 1
    assert data["query"] == "test query"


@pytest.mark.asyncio
@patch("knowledge.routes.search.SearchService")
async def test_search_with_options(MockService, client: AsyncClient):
    """Test search with all options."""
    instance = MockService.return_value
    instance.search = AsyncMock(return_value=_make_search_response())

    response = await client.post(
        "/api/v1/search",
        json={
            "query": "test query",
            "collection_ids": ["coll-1"],
            "top_k": 5,
            "threshold": 0.8,
            "distance_type": "cosine",
            "filters": {"category": "test"},
            "include_content": True,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.search.SearchService")
async def test_search_no_results(MockService, client: AsyncClient):
    """Test search with no results."""
    instance = MockService.return_value
    instance.search = AsyncMock(return_value=_make_search_response(results=[]))

    response = await client.post(
        "/api/v1/search",
        json={"query": "no match"},
    )
    assert response.status_code == 200
    assert response.json()["total_results"] == 0


# ============================================================
# POST /search/collections/{collection_id}
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.search.SearchService")
async def test_search_collection(MockService, client: AsyncClient):
    """Test search within a specific collection."""
    instance = MockService.return_value
    instance.search = AsyncMock(return_value=_make_search_response())

    coll_id = str(uuid4())
    response = await client.post(
        f"/api/v1/search/collections/{coll_id}",
        json={"query": "test query"},
    )
    assert response.status_code == 200

    # Verify that the collection_ids were overridden
    call_args = instance.search.call_args
    request_arg = call_args[0][1]  # The SearchRequest arg
    assert request_arg.collection_ids == [coll_id]


@pytest.mark.asyncio
@patch("knowledge.routes.search.SearchService")
async def test_search_collection_with_slug(MockService, client: AsyncClient):
    """Test search using collection slug."""
    instance = MockService.return_value
    instance.search = AsyncMock(return_value=_make_search_response())

    response = await client.post(
        "/api/v1/search/collections/my-collection",
        json={"query": "test query"},
    )
    assert response.status_code == 200
