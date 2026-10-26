# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for collection invitation routes (knowledge/routes/collection_invitations.py)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from knowledge.models.enums import CollaboratorPermission, InvitationStatus
from tests.conftest import TEST_USER_ID


def _make_mock_collection(**overrides):
    """Create a mock collection."""
    coll = MagicMock()
    coll.id = overrides.get("id", uuid4())
    coll.name = overrides.get("name", "Test Collection")
    return coll


def _make_mock_invitation(**overrides):
    """Create a mock invitation."""
    inv = MagicMock()
    inv.id = overrides.get("id", uuid4())
    inv.collection_id = overrides.get("collection_id", uuid4())
    inv.email = overrides.get("email", "invitee@example.com")
    inv.permission = overrides.get("permission", CollaboratorPermission.READ)
    inv.status = overrides.get("status", InvitationStatus.PENDING)
    inv.invited_by = overrides.get("invited_by", TEST_USER_ID)
    inv.token = overrides.get("token", "test-token-123")
    inv.is_valid = overrides.get("is_valid", True)
    inv.is_expired = overrides.get("is_expired", False)
    return inv


def _make_mock_collaborator(**overrides):
    """Create a mock collaborator."""
    collab = MagicMock()
    collab.id = overrides.get("id", uuid4())
    collab.collection_id = overrides.get("collection_id", uuid4())
    collab.user_id = overrides.get("user_id", uuid4())
    collab.permission = overrides.get("permission", CollaboratorPermission.READ)
    return collab


# ============================================================
# list_invitations (collection-scoped)
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_list_invitations_success(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test listing invitations."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_admin = AsyncMock(return_value=True)

    invs = [_make_mock_invitation(collection_id=coll_id)]
    MockInvService.return_value.list_for_collection = AsyncMock(return_value=invs)

    response = await client.get(f"/api/v1/collections/{coll_id}/invitations")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_list_invitations_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test listing invitations on non-existent collection."""
    coll_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.get(f"/api/v1/collections/{coll_id}/invitations")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_list_invitations_no_admin(MockCollService, MockAccessService, client: AsyncClient):
    """Test listing invitations without admin access."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_admin = AsyncMock(return_value=False)

    response = await client.get(f"/api/v1/collections/{coll_id}/invitations")
    assert response.status_code == 403


# ============================================================
# create_invitation
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_create_invitation_success(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test creating an invitation."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    inv = _make_mock_invitation(collection_id=coll_id)
    MockInvService.return_value.create = AsyncMock(return_value=inv)

    response = await client.post(
        f"/api/v1/collections/{coll_id}/invitations",
        json={"email": "test@example.com", "permission": "read"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_create_invitation_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test creating invitation on non-existent collection."""
    coll_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.post(
        f"/api/v1/collections/{coll_id}/invitations",
        json={"email": "test@example.com", "permission": "read"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_create_invitation_no_invite_permission(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test creating invitation without invite permission."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=False)

    response = await client.post(
        f"/api/v1/collections/{coll_id}/invitations",
        json={"email": "test@example.com", "permission": "read"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_create_invitation_conflict(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test creating duplicate invitation raises conflict."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)
    MockInvService.return_value.create = AsyncMock(side_effect=ValueError("Already invited"))

    response = await client.post(
        f"/api/v1/collections/{coll_id}/invitations",
        json={"email": "test@example.com", "permission": "read"},
    )
    assert response.status_code == 409


# ============================================================
# revoke_invitation
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_revoke_invitation_success(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test revoking an invitation."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    inv = _make_mock_invitation(id=inv_id, collection_id=coll_id)
    MockInvService.return_value.get_by_id = AsyncMock(return_value=inv)
    MockInvService.return_value.revoke = AsyncMock(return_value=True)

    response = await client.delete(f"/api/v1/collections/{coll_id}/invitations/{inv_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_revoke_invitation_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test revoking invitation on non-existent collection."""
    coll_id = uuid4()
    inv_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.delete(f"/api/v1/collections/{coll_id}/invitations/{inv_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_revoke_invitation_no_permission(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test revoking invitation without permission."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=False)

    response = await client.delete(f"/api/v1/collections/{coll_id}/invitations/{inv_id}")
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_revoke_invitation_not_found(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test revoking non-existent invitation."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)
    MockInvService.return_value.get_by_id = AsyncMock(return_value=None)

    response = await client.delete(f"/api/v1/collections/{coll_id}/invitations/{inv_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_revoke_invitation_wrong_collection(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test revoking invitation that belongs to different collection."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    # Invitation belongs to a different collection
    inv = _make_mock_invitation(id=inv_id, collection_id=uuid4())
    MockInvService.return_value.get_by_id = AsyncMock(return_value=inv)

    response = await client.delete(f"/api/v1/collections/{coll_id}/invitations/{inv_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_revoke_invitation_already_processed(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test revoking already processed invitation."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    inv = _make_mock_invitation(id=inv_id, collection_id=coll_id)
    MockInvService.return_value.get_by_id = AsyncMock(return_value=inv)
    MockInvService.return_value.revoke = AsyncMock(return_value=False)

    response = await client.delete(f"/api/v1/collections/{coll_id}/invitations/{inv_id}")
    assert response.status_code == 400


# ============================================================
# resend_invitation
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_resend_invitation_success(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test resending an invitation."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    inv = _make_mock_invitation(id=inv_id, collection_id=coll_id)
    MockInvService.return_value.get_by_id = AsyncMock(return_value=inv)
    MockInvService.return_value.resend = AsyncMock(return_value=inv)

    response = await client.post(f"/api/v1/collections/{coll_id}/invitations/{inv_id}/resend")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_resend_invitation_collection_not_found(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test resending invitation on non-existent collection."""
    coll_id = uuid4()
    inv_id = uuid4()
    MockCollService.return_value.get_accessible = AsyncMock(return_value=None)

    response = await client.post(f"/api/v1/collections/{coll_id}/invitations/{inv_id}/resend")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_resend_invitation_no_permission(
    MockCollService, MockAccessService, client: AsyncClient
):
    """Test resending invitation without permission."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=False)

    response = await client.post(f"/api/v1/collections/{coll_id}/invitations/{inv_id}/resend")
    assert response.status_code == 403


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_resend_invitation_not_found(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test resending non-existent invitation."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)
    MockInvService.return_value.get_by_id = AsyncMock(return_value=None)

    response = await client.post(f"/api/v1/collections/{coll_id}/invitations/{inv_id}/resend")
    assert response.status_code == 404


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
@patch("knowledge.routes.collection_invitations.CollectionAccessService")
@patch("knowledge.routes.collection_invitations.CollectionService")
async def test_resend_invitation_already_processed(
    MockCollService, MockAccessService, MockInvService, client: AsyncClient
):
    """Test resending already processed invitation."""
    coll_id = uuid4()
    inv_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    MockCollService.return_value.get_accessible = AsyncMock(return_value=coll)
    MockAccessService.return_value.can_invite = AsyncMock(return_value=True)

    inv = _make_mock_invitation(id=inv_id, collection_id=coll_id)
    MockInvService.return_value.get_by_id = AsyncMock(return_value=inv)
    MockInvService.return_value.resend = AsyncMock(return_value=None)

    response = await client.post(f"/api/v1/collections/{coll_id}/invitations/{inv_id}/resend")
    assert response.status_code == 400


# ============================================================
# Public routes: get_invitation
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionService")
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
async def test_get_invitation_by_token(MockInvService, MockCollService, client: AsyncClient):
    """Test getting an invitation by token."""
    coll_id = uuid4()
    inv = _make_mock_invitation(collection_id=coll_id)
    MockInvService.return_value.get_by_token = AsyncMock(return_value=inv)

    coll = _make_mock_collection(id=coll_id, name="My Collection")
    MockCollService.return_value.get_by_id_global = AsyncMock(return_value=coll)

    response = await client.get("/api/v1/collection-invites/test-token-123")
    assert response.status_code == 200
    data = response.json()
    assert data["collection_name"] == "My Collection"


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionService")
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
async def test_get_invitation_by_token_no_collection(
    MockInvService, MockCollService, client: AsyncClient
):
    """Test getting invitation when collection is missing."""
    coll_id = uuid4()
    inv = _make_mock_invitation(collection_id=coll_id)
    MockInvService.return_value.get_by_token = AsyncMock(return_value=inv)
    MockCollService.return_value.get_by_id_global = AsyncMock(return_value=None)

    response = await client.get("/api/v1/collection-invites/test-token-123")
    assert response.status_code == 200
    assert response.json()["collection_name"] == "Unknown Collection"


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
async def test_get_invitation_by_token_not_found(MockInvService, client: AsyncClient):
    """Test getting non-existent invitation by token."""
    MockInvService.return_value.get_by_token = AsyncMock(return_value=None)

    response = await client.get("/api/v1/collection-invites/invalid-token")
    assert response.status_code == 404


# ============================================================
# Public routes: accept_invitation
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
async def test_accept_invitation_success(MockInvService, client: AsyncClient):
    """Test accepting an invitation."""
    coll_id = uuid4()
    inv = _make_mock_invitation(collection_id=coll_id)
    collab = _make_mock_collaborator(collection_id=coll_id)

    MockInvService.return_value.accept = AsyncMock(return_value=(inv, collab))

    response = await client.post("/api/v1/collection-invites/test-token/accept")
    assert response.status_code == 200
    assert response.json()["message"] == "Invitation accepted successfully"


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
async def test_accept_invitation_invalid(MockInvService, client: AsyncClient):
    """Test accepting invalid invitation raises error."""
    MockInvService.return_value.accept = AsyncMock(side_effect=ValueError("Invitation expired"))

    response = await client.post("/api/v1/collection-invites/expired-token/accept")
    assert response.status_code == 400


@pytest.mark.asyncio
@patch("knowledge.routes.collection_invitations.CollectionInvitationService")
async def test_accept_invitation_not_found(MockInvService, client: AsyncClient):
    """Test accepting non-existent invitation."""
    MockInvService.return_value.accept = AsyncMock(return_value=None)

    response = await client.post("/api/v1/collection-invites/nonexistent/accept")
    assert response.status_code == 404
