# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for collaborator routes (knowledge/routes/collaborators.py)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from knowledge.models.enums import CollaboratorPermission
from tests.conftest import TEST_USER_ID


def _make_mock_collection(**overrides):
    """Create a mock collection."""
    coll = MagicMock()
    coll.id = overrides.get("id", uuid4())
    coll.name = overrides.get("name", "Test Collection")
    coll.owner_id = overrides.get("owner_id", TEST_USER_ID)
    return coll


def _make_mock_collaborator(**overrides):
    """Create a mock collaborator."""
    collab = MagicMock()
    collab.id = overrides.get("id", uuid4())
    collab.collection_id = overrides.get("collection_id", uuid4())
    collab.user_id = overrides.get("user_id", uuid4())
    collab.permission = overrides.get("permission", CollaboratorPermission.READ)
    collab.invited_by = overrides.get("invited_by", TEST_USER_ID)
    return collab


# ============================================================
# list_collaborators
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_list_collaborators_success(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test listing collaborators."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_read = AsyncMock(return_value=True)

    collabs = [_make_mock_collaborator(collection_id=coll_id)]
    MockCollabService.return_value.list = AsyncMock(return_value=collabs)

    response = await client.get(f"/api/v1/collections/{coll_id}/collaborators")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_list_collaborators_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test listing collaborators on non-existent collection."""
    coll_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.get(f"/api/v1/collections/{coll_id}/collaborators")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_list_collaborators_no_read_access(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test listing collaborators without read access."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_read = AsyncMock(return_value=False)

    response = await client.get(f"/api/v1/collections/{coll_id}/collaborators")
    assert response.status_code == 403


# ============================================================
# add_collaborator
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_add_collaborator_success(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test adding a collaborator."""
    coll_id = uuid4()
    user_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    collab = _make_mock_collaborator(collection_id=coll_id, user_id=user_id)
    MockCollabService.return_value.add = AsyncMock(return_value=collab)

    response = await client.post(
        f"/api/v1/collections/{coll_id}/collaborators",
        json={"user_id": str(user_id), "permission": "read"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_add_collaborator_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test adding collaborator to non-existent collection."""
    coll_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.post(
        f"/api/v1/collections/{coll_id}/collaborators",
        json={"user_id": str(uuid4()), "permission": "read"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_add_collaborator_no_invite_permission(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test adding collaborator without invite permission."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=False)

    response = await client.post(
        f"/api/v1/collections/{coll_id}/collaborators",
        json={"user_id": str(uuid4()), "permission": "read"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_add_self_as_collaborator(MockCollService, MockAccessService, client: AsyncClient):
    """Test cannot add self as collaborator."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    response = await client.post(
        f"/api/v1/collections/{coll_id}/collaborators",
        json={"user_id": str(TEST_USER_ID), "permission": "read"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_add_collaborator_already_exists(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test adding collaborator that already exists raises conflict."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)
    MockCollabService.return_value.add = AsyncMock(side_effect=ValueError("Already a collaborator"))

    response = await client.post(
        f"/api/v1/collections/{coll_id}/collaborators",
        json={"user_id": str(uuid4()), "permission": "read"},
    )
    assert response.status_code == 409


# ============================================================
# update_collaborator
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_update_collaborator_success(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test updating a collaborator."""
    coll_id = uuid4()
    user_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    collab = _make_mock_collaborator(
        collection_id=coll_id, user_id=user_id, permission=CollaboratorPermission.WRITE
    )
    MockCollabService.return_value.update_permission = AsyncMock(return_value=collab)

    response = await client.patch(
        f"/api/v1/collections/{coll_id}/collaborators/{user_id}",
        json={"permission": "write"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_update_collaborator_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test updating collaborator on non-existent collection."""
    coll_id = uuid4()
    user_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.patch(
        f"/api/v1/collections/{coll_id}/collaborators/{user_id}",
        json={"permission": "write"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_update_collaborator_no_permission(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test updating collaborator without admin permission."""
    coll_id = uuid4()
    user_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=False)

    response = await client.patch(
        f"/api/v1/collections/{coll_id}/collaborators/{user_id}",
        json={"permission": "write"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_update_collaborator_not_found(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test updating non-existent collaborator."""
    coll_id = uuid4()
    user_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)
    MockCollabService.return_value.update_permission = AsyncMock(return_value=None)

    response = await client.patch(
        f"/api/v1/collections/{coll_id}/collaborators/{user_id}",
        json={"permission": "write"},
    )
    assert response.status_code == 404


# ============================================================
# remove_collaborator
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_remove_collaborator_self(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test removing yourself as collaborator."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockCollabService.return_value.remove = AsyncMock(return_value=True)

    response = await client.delete(f"/api/v1/collections/{coll_id}/collaborators/{TEST_USER_ID}")
    assert response.status_code == 204


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_remove_collaborator_admin(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test admin removing another collaborator."""
    coll_id = uuid4()
    user_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)
    MockCollabService.return_value.remove = AsyncMock(return_value=True)

    response = await client.delete(f"/api/v1/collections/{coll_id}/collaborators/{user_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_remove_collaborator_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test removing collaborator from non-existent collection."""
    coll_id = uuid4()
    user_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.delete(f"/api/v1/collections/{coll_id}/collaborators/{user_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_remove_collaborator_no_permission(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test removing another collaborator without admin permission."""
    coll_id = uuid4()
    user_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=False)

    response = await client.delete(f"/api/v1/collections/{coll_id}/collaborators/{user_id}")
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collaborators.CollaboratorService")
@patch("knowledge.routes.collaborators.CollectionAccessService")
@patch("knowledge.routes.collaborators.CollectionService")
async def test_remove_collaborator_not_found(
    MockCollService, MockAccessService, MockCollabService, client: AsyncClient
):
    """Test removing non-existent collaborator."""
    coll_id = uuid4()
    user_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)
    MockCollabService.return_value.remove = AsyncMock(return_value=False)

    response = await client.delete(f"/api/v1/collections/{coll_id}/collaborators/{user_id}")
    assert response.status_code == 404
