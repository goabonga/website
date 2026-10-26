# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for SearchService: semantic search with mock DB and embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from knowledge.schemas.search import SearchRequest, SearchResponse
from knowledge.services.search import SearchService

# ============================================================
# search - basic scenarios
# ============================================================


class TestSearch:
    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_with_collection_ids(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        # Embedding service
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        # Collection service
        mock_coll_service = AsyncMock()
        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service.get_by_id_or_slug = AsyncMock(return_value=mock_collection)
        MockCollectionService.return_value = mock_coll_service

        # DB result for the search query
        mock_row = MagicMock()
        mock_row.id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        mock_row.collection_id = collection_id
        mock_row.collection_slug = "test-col"
        mock_row.content = "test content"
        mock_row.score = 0.95
        mock_row.doc_metadata = {"key": "value"}
        mock_row.source_type = "text"
        mock_row.source_ref = None
        mock_row.created_at = "2026-01-01"

        result_mock = MagicMock()
        result_mock.all.return_value = [mock_row]
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        request = SearchRequest(
            query="test query",
            collection_ids=[str(collection_id)],
            top_k=5,
            threshold=0.5,
        )
        response = await service.search(tenant_id, request)

        assert isinstance(response, SearchResponse)
        assert response.total_results == 1
        assert response.query == "test query"
        assert response.results[0].score == 0.95
        assert response.results[0].content == "test content"
        mock_embed_service.embed_text.assert_called_once_with("test query")

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_without_collection_ids_searches_all(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service = AsyncMock()
        mock_coll_service.list = AsyncMock(return_value=[mock_collection])
        MockCollectionService.return_value = mock_coll_service

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        request = SearchRequest(query="test query")
        response = await service.search(tenant_id, request)

        assert response.total_results == 0
        assert response.results == []
        mock_coll_service.list.assert_called_once_with(tenant_id)

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_no_collections_returns_empty(
        self, MockCollectionService, mock_get_embed, mock_db, tenant_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_coll_service = AsyncMock()
        mock_coll_service.list = AsyncMock(return_value=[])
        MockCollectionService.return_value = mock_coll_service

        service = SearchService(mock_db)
        request = SearchRequest(query="test query")
        response = await service.search(tenant_id, request)

        assert response.total_results == 0
        assert response.results == []
        assert response.query == "test query"

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_with_collection_ids_some_not_found(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        """When some collection IDs resolve but others don't, search those found."""
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service = AsyncMock()
        # First slug found, second not found
        mock_coll_service.get_by_id_or_slug = AsyncMock(side_effect=[mock_collection, None])
        MockCollectionService.return_value = mock_coll_service

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        request = SearchRequest(
            query="test query",
            collection_ids=["valid-slug", "invalid-slug"],
        )
        response = await service.search(tenant_id, request)

        assert response.total_results == 0

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_with_collection_ids_all_not_found(
        self, MockCollectionService, mock_get_embed, mock_db, tenant_id
    ):
        """When no collection IDs resolve, return empty response."""
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_coll_service = AsyncMock()
        mock_coll_service.get_by_id_or_slug = AsyncMock(return_value=None)
        MockCollectionService.return_value = mock_coll_service

        service = SearchService(mock_db)
        request = SearchRequest(
            query="test query",
            collection_ids=["nonexistent-1", "nonexistent-2"],
        )
        response = await service.search(tenant_id, request)

        assert response.total_results == 0
        assert response.results == []

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_include_content_false(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service = AsyncMock()
        mock_coll_service.get_by_id_or_slug = AsyncMock(return_value=mock_collection)
        MockCollectionService.return_value = mock_coll_service

        mock_row = MagicMock()
        mock_row.id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        mock_row.collection_id = collection_id
        mock_row.collection_slug = "test-col"
        mock_row.content = "should be hidden"
        mock_row.score = 0.9
        mock_row.doc_metadata = {}

        result_mock = MagicMock()
        result_mock.all.return_value = [mock_row]
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        request = SearchRequest(
            query="test",
            collection_ids=[str(collection_id)],
            include_content=False,
        )
        response = await service.search(tenant_id, request)

        assert response.results[0].content == ""

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_l2_distance_type(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service = AsyncMock()
        mock_coll_service.get_by_id_or_slug = AsyncMock(return_value=mock_collection)
        MockCollectionService.return_value = mock_coll_service

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        request = SearchRequest(
            query="test",
            collection_ids=[str(collection_id)],
            distance_type="l2",
        )
        response = await service.search(tenant_id, request)
        assert response.total_results == 0

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_inner_product_distance_type(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service = AsyncMock()
        mock_coll_service.get_by_id_or_slug = AsyncMock(return_value=mock_collection)
        MockCollectionService.return_value = mock_coll_service

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        request = SearchRequest(
            query="test",
            collection_ids=[str(collection_id)],
            distance_type="inner_product",
        )
        response = await service.search(tenant_id, request)
        assert response.total_results == 0


# ============================================================
# search_collection
# ============================================================


class TestSearchCollection:
    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_delegates_to_search(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service = AsyncMock()
        mock_coll_service.get_by_id_or_slug = AsyncMock(return_value=mock_collection)
        MockCollectionService.return_value = mock_coll_service

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        results = await service.search_collection(
            tenant_id, str(collection_id), "my query", top_k=5, threshold=0.8
        )
        assert results == []
        mock_embed_service.embed_text.assert_called_once()

    @patch("knowledge.services.search.get_embedding_service")
    @patch("knowledge.services.search.CollectionService")
    async def test_search_collection_with_filters(
        self, MockCollectionService, mock_get_embed, mock_db, collection_id, tenant_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.id = collection_id
        mock_coll_service = AsyncMock()
        mock_coll_service.get_by_id_or_slug = AsyncMock(return_value=mock_collection)
        MockCollectionService.return_value = mock_coll_service

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = SearchService(mock_db)
        results = await service.search_collection(
            tenant_id,
            "my-slug",
            "query",
            filters={"source_type": "pdf"},
        )
        assert results == []
