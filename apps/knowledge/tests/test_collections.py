# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for collections API endpoints (mock-based, no aiosqlite)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from knowledge.models.enums import OwnerType
from tests.conftest import TEST_TENANT_ID, TEST_USER_ID


def _make_mock_collection(**overrides):
    """Create a mock collection ORM object with realistic attributes."""
    coll = MagicMock()
    coll.id = overrides.get("id", uuid4())
    coll.tenant_id = overrides.get("tenant_id", TEST_TENANT_ID)
    coll.owner_type = overrides.get("owner_type", OwnerType.USER)
    coll.owner_id = overrides.get("owner_id", TEST_USER_ID)
    coll.organization_id = overrides.get("organization_id")
    coll.name = overrides.get("name", "Test Collection")
    coll.slug = overrides.get("slug", "test-collection")
    coll.description = overrides.get("description", "A test collection")
    coll.embedding_model = overrides.get("embedding_model", "text-embedding-3-small")
    coll.dimension = overrides.get("dimension", 1536)
    coll.metadata_schema = overrides.get("metadata_schema")
    coll.document_count = overrides.get("document_count", 0)
    coll.created_at = overrides.get("created_at", datetime.now(UTC))
    coll.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return coll


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_create_collection(MockService, client: AsyncClient):
    """Test creating a collection."""
    mock_collection = _make_mock_collection(name="Test Collection", slug="test-collection")

    instance = MockService.return_value
    instance.get_by_slug_for_owner = AsyncMock(return_value=None)
    instance.create_for_owner = AsyncMock(return_value=mock_collection)

    response = await client.post(
        "/api/v1/collections",
        json={
            "name": "Test Collection",
            "slug": "test-collection",
            "description": "A test collection",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Collection"
    assert data["slug"] == "test-collection"
    assert data["document_count"] == 0


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_create_duplicate_collection(MockService, client: AsyncClient):
    """Test creating a collection with duplicate slug fails."""
    existing = _make_mock_collection(slug="duplicate-slug")

    instance = MockService.return_value
    instance.get_by_slug_for_owner = AsyncMock(return_value=existing)

    response = await client.post(
        "/api/v1/collections",
        json={"name": "Second", "slug": "duplicate-slug"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_list_collections(MockService, client: AsyncClient):
    """Test listing collections."""
    collections = [
        _make_mock_collection(name="Collection 1", slug="collection-1"),
        _make_mock_collection(name="Collection 2", slug="collection-2"),
    ]

    instance = MockService.return_value
    instance.list_accessible = AsyncMock(return_value=collections)

    response = await client.get("/api/v1/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_get_collection_by_id(MockService, client: AsyncClient):
    """Test getting a collection by ID."""
    coll_id = uuid4()
    mock_collection = _make_mock_collection(id=coll_id)

    instance = MockService.return_value
    instance.get_accessible = AsyncMock(return_value=mock_collection)

    response = await client.get(f"/api/v1/collections/{coll_id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(coll_id)


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_get_collection_by_slug(MockService, client: AsyncClient):
    """Test getting a collection by slug."""
    mock_collection = _make_mock_collection(slug="slug-test")

    instance = MockService.return_value
    instance.get_by_slug_for_owner = AsyncMock(return_value=mock_collection)

    response = await client.get("/api/v1/collections/slug-test")
    assert response.status_code == 200
    assert response.json()["slug"] == "slug-test"


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_get_nonexistent_collection(MockService, client: AsyncClient):
    """Test getting a nonexistent collection returns 404."""
    instance = MockService.return_value
    instance.get_by_slug_for_owner = AsyncMock(return_value=None)
    instance.get_accessible = AsyncMock(return_value=None)

    response = await client.get("/api/v1/collections/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_update_collection(MockService, MockAccessService, client: AsyncClient):
    """Test updating a collection."""
    coll_id = uuid4()
    mock_collection = _make_mock_collection(id=coll_id, name="Update Test")

    service = MockService.return_value
    service.get_accessible = AsyncMock(return_value=mock_collection)

    access = MockAccessService.return_value
    access.can_write = AsyncMock(return_value=True)

    response = await client.patch(
        f"/api/v1/collections/{coll_id}",
        json={"name": "Updated Name", "description": "New description"},
    )
    assert response.status_code == 200
    assert mock_collection.name == "Updated Name"
    assert mock_collection.description == "New description"


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_delete_collection(MockService, MockAccessService, client: AsyncClient):
    """Test deleting a collection."""
    coll_id = uuid4()
    mock_collection = _make_mock_collection(id=coll_id)

    service = MockService.return_value
    service.get_accessible = AsyncMock(return_value=mock_collection)

    access = MockAccessService.return_value
    access.can_delete = AsyncMock(return_value=True)

    response = await client.delete(f"/api/v1/collections/{coll_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_delete_collection_not_found(MockService, MockAccessService, client: AsyncClient):
    """Test deleting a nonexistent collection returns 404."""
    coll_id = uuid4()
    service = MockService.return_value
    service.get_accessible = AsyncMock(return_value=None)

    response = await client.delete(f"/api/v1/collections/{coll_id}")
    assert response.status_code == 404


# ============================================================
# Additional tests for missing coverage
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_create_collection_with_organization(
    MockService, MockAccessService, client: AsyncClient
):
    """Test creating a collection under an organization (lines 48-62)."""
    org_id = uuid4()
    mock_collection = _make_mock_collection(owner_type=OwnerType.ORGANIZATION, owner_id=org_id)

    service = MockService.return_value
    service.get_by_slug_for_owner = AsyncMock(return_value=None)
    service.create_for_owner = AsyncMock(return_value=mock_collection)

    access = MockAccessService.return_value
    access.check_org_can_create_collection = AsyncMock(return_value=True)

    response = await client.post(
        f"/api/v1/collections?organization_id={org_id}",
        json={"name": "Org Collection", "slug": "org-collection"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_create_collection_org_no_permission(
    MockService, MockAccessService, client: AsyncClient
):
    """Test creating org collection without permission (line 58-62)."""
    org_id = uuid4()

    access = MockAccessService.return_value
    access.check_org_can_create_collection = AsyncMock(return_value=False)

    response = await client.post(
        f"/api/v1/collections?organization_id={org_id}",
        json={"name": "Org Collection", "slug": "org-collection"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_list_collections_user_only(MockService, client: AsyncClient):
    """Test listing only personal collections (owner_type=user, line 111-113)."""
    collections = [_make_mock_collection(owner_type=OwnerType.USER)]
    instance = MockService.return_value
    instance.list_for_owner = AsyncMock(return_value=collections)

    response = await client.get("/api/v1/collections?owner_type=user")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_list_collections_organization_with_id(MockService, client: AsyncClient, mock_db):
    """Test listing org collections with org ID (lines 116-135)."""
    org_id = uuid4()
    collections = [_make_mock_collection(owner_type=OwnerType.ORGANIZATION, owner_id=org_id)]

    # Mock the DB check for org membership
    from tests.conftest import _make_result

    membership = MagicMock()
    membership.organization_id = org_id
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=membership))

    instance = MockService.return_value
    instance.list_for_owner = AsyncMock(return_value=collections)

    response = await client.get(f"/api/v1/collections?organization_id={org_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_list_collections_organization_not_member(MockService, client: AsyncClient, mock_db):
    """Test listing org collections when not a member (line 128-132)."""
    org_id = uuid4()

    from tests.conftest import _make_result

    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await client.get(f"/api/v1/collections?organization_id={org_id}")
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_list_collections_organization_type_no_id(MockService, client: AsyncClient):
    """Test listing org collections without specific org ID (lines 136-145)."""
    collections = [_make_mock_collection(owner_type=OwnerType.ORGANIZATION)]
    instance = MockService.return_value
    instance.list_accessible = AsyncMock(return_value=collections)

    response = await client.get("/api/v1/collections?owner_type=organization")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_get_collection_by_slug_not_found_check_orgs(
    MockService, client: AsyncClient, mock_db
):
    """Test getting collection by slug falls back to org search (lines 186-204)."""
    instance = MockService.return_value
    # Not found as personal collection
    instance.get_by_slug_for_owner = AsyncMock(return_value=None)

    # Mock DB: user has org memberships

    org_id = uuid4()
    row = MagicMock()
    row.__getitem__ = MagicMock(side_effect=lambda i: org_id if i == 0 else None)
    result = MagicMock()
    result.all.return_value = [row]
    mock_db.execute = AsyncMock(return_value=result)

    # First call returns None (personal), subsequent calls for each org
    # The service is called multiple times with different parameters
    found_coll = _make_mock_collection(slug="org-slug")
    # Return None first (personal slug check), then found for org
    instance.get_by_slug_for_owner = AsyncMock(side_effect=[None, found_coll])

    response = await client.get("/api/v1/collections/org-slug")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_get_collection_by_slug_org_loop_continues(MockService, client: AsyncClient, mock_db):
    """Test org slug search loops past non-matching org (branch 203->199)."""
    instance = MockService.return_value

    # Mock DB: user has 2 org memberships

    org_id_1 = uuid4()
    org_id_2 = uuid4()
    row1 = MagicMock()
    row1.__getitem__ = MagicMock(side_effect=lambda i: org_id_1 if i == 0 else None)
    row2 = MagicMock()
    row2.__getitem__ = MagicMock(side_effect=lambda i: org_id_2 if i == 0 else None)
    result = MagicMock()
    result.all.return_value = [row1, row2]
    mock_db.execute = AsyncMock(return_value=result)

    found_coll = _make_mock_collection(slug="multi-org-slug")
    # personal: None, org1: None (loop continues), org2: found
    instance.get_by_slug_for_owner = AsyncMock(side_effect=[None, None, found_coll])

    response = await client.get("/api/v1/collections/multi-org-slug")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_update_collection_not_found(MockService, MockAccessService, client: AsyncClient):
    """Test updating a non-existent collection (line 235)."""
    coll_id = uuid4()
    service = MockService.return_value
    service.get_accessible = AsyncMock(return_value=None)

    response = await client.patch(
        f"/api/v1/collections/{coll_id}",
        json={"name": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_update_collection_no_write_permission(
    MockService, MockAccessService, client: AsyncClient
):
    """Test updating a collection without write permission (line 243)."""
    coll_id = uuid4()
    mock_collection = _make_mock_collection(id=coll_id)

    service = MockService.return_value
    service.get_accessible = AsyncMock(return_value=mock_collection)

    access = MockAccessService.return_value
    access.can_write = AsyncMock(return_value=False)

    response = await client.patch(
        f"/api/v1/collections/{coll_id}",
        json={"name": "Updated"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionAccessService")
@patch("knowledge.routes.collections.CollectionService")
async def test_delete_collection_no_permission(MockService, MockAccessService, client: AsyncClient):
    """Test deleting a collection without delete permission (line 286)."""
    coll_id = uuid4()
    mock_collection = _make_mock_collection(id=coll_id)

    service = MockService.return_value
    service.get_accessible = AsyncMock(return_value=mock_collection)

    access = MockAccessService.return_value
    access.can_delete = AsyncMock(return_value=False)

    response = await client.delete(f"/api/v1/collections/{coll_id}")
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collections.CollectionService")
async def test_list_collections_exclude_shared(MockService, client: AsyncClient):
    """Test listing collections with include_shared=false."""
    collections = [_make_mock_collection()]
    instance = MockService.return_value
    instance.list_accessible = AsyncMock(return_value=collections)

    response = await client.get("/api/v1/collections?include_shared=false")
    assert response.status_code == 200
