# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for DocumentService: hash, CRUD, embedding mocking."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from knowledge.schemas.document import DocumentCreate
from knowledge.services.documents import DocumentService

# ============================================================
# _compute_hash (static, pure)
# ============================================================


class TestComputeHash:
    def test_deterministic(self):
        h1 = DocumentService._compute_hash("hello world")
        h2 = DocumentService._compute_hash("hello world")
        assert h1 == h2

    def test_different_content(self):
        h1 = DocumentService._compute_hash("hello")
        h2 = DocumentService._compute_hash("world")
        assert h1 != h2

    def test_known_sha256(self):
        import hashlib

        expected = hashlib.sha256(b"test content").hexdigest()
        assert DocumentService._compute_hash("test content") == expected


# ============================================================
# create (mock DB + embedding)
# ============================================================


class TestCreate:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_creates_document(self, mock_get_embed, mock_db, make_result, collection_id):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])
        mock_get_embed.return_value = mock_embed_service

        # increment_document_count also calls db.execute
        mock_collection = MagicMock()
        mock_collection.document_count = 0
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))

        service = DocumentService(mock_db)
        data = DocumentCreate(content="hello world")
        await service.create(collection_id, data)

        mock_embed_service.embed_text.assert_called_once_with("hello world")
        mock_db.add.assert_called_once()
        assert mock_db.flush.call_count >= 1

        added_doc = mock_db.add.call_args[0][0]
        assert added_doc.content == "hello world"
        assert added_doc.embedding == [0.1, 0.2, 0.3]
        assert added_doc.collection_id == collection_id
        assert added_doc.content_size == len(b"hello world")
        assert added_doc.embedding_size == 12

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_increments_collection_count(
        self, mock_get_embed, mock_db, make_result, collection_id
    ):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_text = AsyncMock(return_value=[0.1])
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.document_count = 5
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))

        service = DocumentService(mock_db)
        await service.create(collection_id, DocumentCreate(content="test"))

        assert mock_collection.document_count == 6


# ============================================================
# create_batch (mock DB + embedding)
# ============================================================


class TestCreateBatch:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_empty_list(self, mock_get_embed, mock_db):
        mock_embed_service = AsyncMock()
        mock_get_embed.return_value = mock_embed_service

        service = DocumentService(mock_db)
        result = await service.create_batch(UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"), [])
        assert result == []
        mock_embed_service.embed_texts.assert_not_called()

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_batch_creates_all(self, mock_get_embed, mock_db, make_result, collection_id):
        mock_embed_service = AsyncMock()
        mock_embed_service.embed_texts = AsyncMock(return_value=[[0.1], [0.2]])
        mock_get_embed.return_value = mock_embed_service

        mock_collection = MagicMock()
        mock_collection.document_count = 0
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))

        service = DocumentService(mock_db)
        docs = [DocumentCreate(content="doc1"), DocumentCreate(content="doc2")]
        await service.create_batch(collection_id, docs)

        mock_embed_service.embed_texts.assert_called_once_with(["doc1", "doc2"])
        assert mock_db.add.call_count == 2
        assert mock_collection.document_count == 2
        first_added = mock_db.add.call_args_list[0][0][0]
        second_added = mock_db.add.call_args_list[1][0][0]
        assert first_added.content_size == len(b"doc1")
        assert second_added.content_size == len(b"doc2")
        assert first_added.embedding_size == 4
        assert second_added.embedding_size == 4


# ============================================================
# get_by_id
# ============================================================


class TestGetById:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_found(self, mock_get_embed, mock_db, make_result):
        mock_get_embed.return_value = AsyncMock()
        mock_doc = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_doc))

        service = DocumentService(mock_db)
        result = await service.get_by_id(UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))
        assert result is mock_doc

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_not_found(self, mock_get_embed, mock_db):
        mock_get_embed.return_value = AsyncMock()

        service = DocumentService(mock_db)
        result = await service.get_by_id(UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))
        assert result is None


# ============================================================
# delete
# ============================================================


class TestDelete:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_found_and_deleted(self, mock_get_embed, mock_db, make_result, collection_id):
        mock_get_embed.return_value = AsyncMock()
        mock_doc = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document_count = 5

        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_doc),  # get_by_id
                make_result(scalar_one_or_none=mock_collection),  # increment_document_count
            ]
        )

        service = DocumentService(mock_db)
        doc_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        result = await service.delete(doc_id, collection_id)

        assert result is True
        mock_db.delete.assert_called_once_with(mock_doc)
        assert mock_collection.document_count == 4

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_not_found_returns_false(self, mock_get_embed, mock_db, collection_id):
        mock_get_embed.return_value = AsyncMock()

        service = DocumentService(mock_db)
        doc_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        result = await service.delete(doc_id, collection_id)
        assert result is False


# ============================================================
# exists_by_hash
# ============================================================


class TestExistsByHash:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_exists(self, mock_get_embed, mock_db, make_result, collection_id):
        mock_get_embed.return_value = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=make_result(
                scalar_one_or_none=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
            )
        )

        service = DocumentService(mock_db)
        assert await service.exists_by_hash(collection_id, "abc123") is True

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_not_exists(self, mock_get_embed, mock_db, collection_id):
        mock_get_embed.return_value = AsyncMock()

        service = DocumentService(mock_db)
        assert await service.exists_by_hash(collection_id, "abc123") is False


# ============================================================
# list (lines 145-152)
# ============================================================


class TestList:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_returns_documents(self, mock_get_embed, mock_db, make_result, collection_id):
        mock_get_embed.return_value = AsyncMock()
        doc1 = MagicMock()
        doc2 = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[doc1, doc2]))

        service = DocumentService(mock_db)
        result = await service.list(collection_id)
        assert len(result) == 2
        assert result[0] is doc1
        assert result[1] is doc2

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_returns_empty(self, mock_get_embed, mock_db, collection_id):
        mock_get_embed.return_value = AsyncMock()

        service = DocumentService(mock_db)
        result = await service.list(collection_id)
        assert result == []

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_with_offset_limit(self, mock_get_embed, mock_db, make_result, collection_id):
        mock_get_embed.return_value = AsyncMock()
        doc = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[doc]))

        service = DocumentService(mock_db)
        result = await service.list(collection_id, offset=10, limit=5)
        assert len(result) == 1


# ============================================================
# delete_by_collection (lines 185-189)
# ============================================================


class TestDeleteByCollection:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_deletes_all(self, mock_get_embed, mock_db, make_result, collection_id):
        mock_get_embed.return_value = AsyncMock()
        mock_db.execute = AsyncMock(return_value=make_result(rowcount=5))

        service = DocumentService(mock_db)
        count = await service.delete_by_collection(collection_id)
        assert count == 5
        mock_db.flush.assert_called_once()

    @patch("knowledge.services.documents.get_embedding_service")
    async def test_deletes_none(self, mock_get_embed, mock_db, collection_id):
        mock_get_embed.return_value = AsyncMock()

        service = DocumentService(mock_db)
        count = await service.delete_by_collection(collection_id)
        assert count == 0


# ============================================================
# get_by_id with collection_id filter
# ============================================================


class TestGetByIdWithCollectionFilter:
    @patch("knowledge.services.documents.get_embedding_service")
    async def test_found_with_collection_id(
        self, mock_get_embed, mock_db, make_result, collection_id
    ):
        mock_get_embed.return_value = AsyncMock()
        mock_doc = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_doc))

        service = DocumentService(mock_db)
        result = await service.get_by_id(
            UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
            collection_id=collection_id,
        )
        assert result is mock_doc
