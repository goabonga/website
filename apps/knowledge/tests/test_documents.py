# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for documents API endpoints (mock-based, no aiosqlite)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from knowledge.models.enums import OwnerType
from tests.conftest import TEST_TENANT_ID


def _make_mock_collection(**overrides):
    """Create a mock collection ORM object."""
    coll = MagicMock()
    coll.id = overrides.get("id", uuid4())
    coll.tenant_id = overrides.get("tenant_id", TEST_TENANT_ID)
    coll.owner_type = OwnerType.ORGANIZATION
    coll.owner_id = TEST_TENANT_ID
    coll.organization_id = TEST_TENANT_ID
    coll.name = overrides.get("name", "Doc Test Collection")
    coll.slug = overrides.get("slug", "doc-test")
    return coll


def _make_mock_document(collection_id, **overrides):
    """Create a mock document ORM object."""
    doc = MagicMock()
    doc.id = overrides.get("id", uuid4())
    doc.collection_id = collection_id
    doc.content = overrides.get("content", "Test document content")
    doc.doc_metadata = overrides.get("doc_metadata", {})
    doc.source_type = overrides.get("source_type")
    doc.source_ref = overrides.get("source_ref")
    doc.created_at = overrides.get("created_at", datetime.now(UTC))
    doc.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return doc


@pytest.mark.asyncio
@patch("knowledge.routes.documents.DocumentService")
@patch("knowledge.routes.documents.CollectionService")
async def test_add_single_document(MockCollService, MockDocService, client: AsyncClient):
    """Test adding a single document."""
    coll = _make_mock_collection()

    coll_instance = MockCollService.return_value
    coll_instance.get_by_id_or_slug = AsyncMock(return_value=coll)

    mock_doc = _make_mock_document(
        coll.id,
        content="This is a test document about Python programming.",
        doc_metadata={"category": "programming", "language": "python"},
    )

    doc_instance = MockDocService.return_value
    doc_instance.create = AsyncMock(return_value=mock_doc)

    response = await client.post(
        "/api/v1/collections/doc-test/documents/single",
        json={
            "content": "This is a test document about Python programming.",
            "metadata": {"category": "programming", "language": "python"},
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "This is a test document about Python programming."
    assert data["metadata"]["category"] == "programming"


@pytest.mark.asyncio
@patch("knowledge.routes.documents.DocumentService")
@patch("knowledge.routes.documents.CollectionService")
async def test_add_multiple_documents(MockCollService, MockDocService, client: AsyncClient):
    """Test adding multiple documents."""
    coll = _make_mock_collection()

    coll_instance = MockCollService.return_value
    coll_instance.get_by_id_or_slug = AsyncMock(return_value=coll)

    mock_docs = [
        _make_mock_document(coll.id, content="Document 1 about FastAPI."),
        _make_mock_document(coll.id, content="Document 2 about databases."),
        _make_mock_document(coll.id, content="Document 3 about testing."),
    ]

    doc_instance = MockDocService.return_value
    doc_instance.create_batch = AsyncMock(return_value=mock_docs)

    response = await client.post(
        "/api/v1/collections/doc-test/documents",
        json={
            "documents": [
                {"content": "Document 1 about FastAPI."},
                {"content": "Document 2 about databases."},
                {"content": "Document 3 about testing."},
            ]
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert len(data) == 3


@pytest.mark.asyncio
@patch("knowledge.routes.documents.DocumentService")
@patch("knowledge.routes.documents.CollectionService")
async def test_list_documents(MockCollService, MockDocService, client: AsyncClient):
    """Test listing documents in a collection."""
    coll = _make_mock_collection()

    coll_instance = MockCollService.return_value
    coll_instance.get_by_id_or_slug = AsyncMock(return_value=coll)

    mock_docs = [
        _make_mock_document(coll.id, content="List test doc 1"),
        _make_mock_document(coll.id, content="List test doc 2"),
    ]

    doc_instance = MockDocService.return_value
    doc_instance.list = AsyncMock(return_value=mock_docs)

    response = await client.get("/api/v1/collections/doc-test/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
@patch("knowledge.routes.documents.CollectionService")
@patch("knowledge.routes.documents.DocumentService")
async def test_get_document_by_id(MockDocService, MockCollService, client: AsyncClient):
    """Test getting a document by ID."""
    coll = _make_mock_collection()
    doc_id = uuid4()
    mock_doc = _make_mock_document(coll.id, id=doc_id, content="Get test document")

    doc_instance = MockDocService.return_value
    doc_instance.get_by_id = AsyncMock(return_value=mock_doc)

    coll_instance = MockCollService.return_value
    coll_instance.get_by_id = AsyncMock(return_value=coll)

    response = await client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(doc_id)


@pytest.mark.asyncio
@patch("knowledge.routes.documents.DocumentService")
@patch("knowledge.routes.documents.CollectionService")
async def test_delete_document(MockCollService, MockDocService, client: AsyncClient):
    """Test deleting a document."""
    coll = _make_mock_collection()
    doc_id = uuid4()

    coll_instance = MockCollService.return_value
    coll_instance.get_by_id_or_slug = AsyncMock(return_value=coll)

    doc_instance = MockDocService.return_value
    doc_instance.delete = AsyncMock(return_value=True)

    response = await client.delete(f"/api/v1/collections/doc-test/documents/{doc_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
@patch("knowledge.routes.documents.CollectionService")
async def test_add_document_to_nonexistent_collection(MockCollService, client: AsyncClient):
    """Test adding document to nonexistent collection fails."""
    coll_instance = MockCollService.return_value
    coll_instance.get_by_id_or_slug = AsyncMock(return_value=None)

    response = await client.post(
        "/api/v1/collections/nonexistent/documents/single",
        json={"content": "Test content"},
    )
    assert response.status_code == 404


# ============================================================
# Additional tests for missing coverage
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.documents.DocumentService")
async def test_get_document_not_found(MockDocService, client: AsyncClient):
    """Test getting a document that doesn't exist (line 116)."""
    doc_id = uuid4()
    doc_instance = MockDocService.return_value
    doc_instance.get_by_id = AsyncMock(return_value=None)

    response = await client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.documents.CollectionService")
@patch("knowledge.routes.documents.DocumentService")
async def test_get_document_collection_not_found(
    MockDocService, MockCollService, client: AsyncClient
):
    """Test getting a document where its collection is not found for tenant (line 125)."""
    coll = _make_mock_collection()
    doc_id = uuid4()
    mock_doc = _make_mock_document(coll.id, id=doc_id)

    doc_instance = MockDocService.return_value
    doc_instance.get_by_id = AsyncMock(return_value=mock_doc)

    # Collection not found for this tenant
    coll_instance = MockCollService.return_value
    coll_instance.get_by_id = AsyncMock(return_value=None)

    response = await client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.documents.DocumentService")
@patch("knowledge.routes.documents.CollectionService")
async def test_delete_document_not_found(MockCollService, MockDocService, client: AsyncClient):
    """Test deleting a document that doesn't exist (line 152)."""
    coll = _make_mock_collection()
    doc_id = uuid4()

    coll_instance = MockCollService.return_value
    coll_instance.get_by_id_or_slug = AsyncMock(return_value=coll)

    doc_instance = MockDocService.return_value
    doc_instance.delete = AsyncMock(return_value=False)

    response = await client.delete(f"/api/v1/collections/doc-test/documents/{doc_id}")
    assert response.status_code == 404
