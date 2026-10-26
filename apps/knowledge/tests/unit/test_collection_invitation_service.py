# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for CollectionInvitationService: create, accept, revoke, list, etc."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from knowledge.models.enums import CollaboratorPermission, InvitationStatus
from knowledge.services.collection_invitations import CollectionInvitationService

# ============================================================
# create
# ============================================================


class TestCreate:
    @patch("knowledge.models.CollectionInvitation.default_expiry", return_value="2026-03-01")
    @patch("knowledge.models.CollectionInvitation.generate_token", return_value="test-token")
    async def test_creates_invitation(
        self, _mock_token, _mock_expiry, mock_db, make_result, collection_id, user_id
    ):
        # get_pending_for_email returns None (no existing)
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))
        service = CollectionInvitationService(mock_db)

        await service.create(
            collection_id, "user@example.com", CollaboratorPermission.READ, user_id
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_raises_if_pending_exists(self, mock_db, make_result, collection_id, user_id):
        existing = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing))
        service = CollectionInvitationService(mock_db)

        with pytest.raises(ValueError, match="already a pending invitation"):
            await service.create(
                collection_id, "user@example.com", CollaboratorPermission.READ, user_id
            )

    @patch("knowledge.models.CollectionInvitation.default_expiry", return_value="2026-03-01")
    @patch("knowledge.models.CollectionInvitation.generate_token", return_value="test-token")
    async def test_create_with_custom_expiry(
        self, _mock_token, _mock_expiry, mock_db, make_result, collection_id, user_id
    ):
        from datetime import UTC, datetime

        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))
        service = CollectionInvitationService(mock_db)
        custom_expiry = datetime(2026, 12, 31, tzinfo=UTC)

        await service.create(
            collection_id,
            "User@Example.com",
            CollaboratorPermission.WRITE,
            user_id,
            expires_at=custom_expiry,
        )

        mock_db.add.assert_called_once()


# ============================================================
# get_by_id
# ============================================================


class TestGetById:
    async def test_found(self, mock_db, make_result):
        invitation = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))
        service = CollectionInvitationService(mock_db)
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        result = await service.get_by_id(inv_id)
        assert result is invitation

    async def test_not_found(self, mock_db):
        service = CollectionInvitationService(mock_db)
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        result = await service.get_by_id(inv_id)
        assert result is None


# ============================================================
# get_by_token
# ============================================================


class TestGetByToken:
    async def test_found(self, mock_db, make_result):
        invitation = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))
        service = CollectionInvitationService(mock_db)
        result = await service.get_by_token("test-token")
        assert result is invitation

    async def test_not_found(self, mock_db):
        service = CollectionInvitationService(mock_db)
        result = await service.get_by_token("nonexistent")
        assert result is None


# ============================================================
# get_pending_for_email
# ============================================================


class TestGetPendingForEmail:
    async def test_found(self, mock_db, make_result, collection_id):
        invitation = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))
        service = CollectionInvitationService(mock_db)
        result = await service.get_pending_for_email(collection_id, "user@example.com")
        assert result is invitation

    async def test_not_found(self, mock_db, collection_id):
        service = CollectionInvitationService(mock_db)
        result = await service.get_pending_for_email(collection_id, "nobody@example.com")
        assert result is None


# ============================================================
# list_for_collection
# ============================================================


class TestListForCollection:
    async def test_returns_all(self, mock_db, make_result, collection_id):
        inv1 = MagicMock()
        inv2 = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[inv1, inv2]))
        service = CollectionInvitationService(mock_db)
        result = await service.list_for_collection(collection_id)
        assert len(result) == 2

    async def test_returns_empty(self, mock_db, collection_id):
        service = CollectionInvitationService(mock_db)
        result = await service.list_for_collection(collection_id)
        assert result == []

    async def test_with_status_filter(self, mock_db, make_result, collection_id):
        inv = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[inv]))
        service = CollectionInvitationService(mock_db)
        result = await service.list_for_collection(collection_id, status=InvitationStatus.PENDING)
        assert len(result) == 1

    async def test_with_offset_limit(self, mock_db, make_result, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[]))
        service = CollectionInvitationService(mock_db)
        result = await service.list_for_collection(collection_id, offset=5, limit=10)
        assert result == []


# ============================================================
# list_pending_for_collection
# ============================================================


class TestListPendingForCollection:
    async def test_delegates_to_list_for_collection(self, mock_db, make_result, collection_id):
        inv = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[inv]))
        service = CollectionInvitationService(mock_db)
        result = await service.list_pending_for_collection(collection_id)
        assert len(result) == 1


# ============================================================
# list_for_email
# ============================================================


class TestListForEmail:
    async def test_returns_invitations(self, mock_db, make_result):
        inv1 = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[inv1]))
        service = CollectionInvitationService(mock_db)
        result = await service.list_for_email("user@example.com")
        assert len(result) == 1

    async def test_returns_empty(self, mock_db):
        service = CollectionInvitationService(mock_db)
        result = await service.list_for_email("nobody@example.com")
        assert result == []

    async def test_with_status_filter(self, mock_db, make_result):
        inv = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[inv]))
        service = CollectionInvitationService(mock_db)
        result = await service.list_for_email("user@example.com", status=InvitationStatus.ACCEPTED)
        assert len(result) == 1


# ============================================================
# list_pending_for_email
# ============================================================


class TestListPendingForEmail:
    async def test_delegates_to_list_for_email(self, mock_db, make_result):
        inv = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[inv]))
        service = CollectionInvitationService(mock_db)
        result = await service.list_pending_for_email("user@example.com")
        assert len(result) == 1


# ============================================================
# accept
# ============================================================


class TestAccept:
    async def test_returns_none_if_token_not_found(self, mock_db, user_id):
        service = CollectionInvitationService(mock_db)
        result = await service.accept("nonexistent-token", user_id)
        assert result is None

    async def test_raises_if_expired(self, mock_db, make_result, user_id):
        invitation = MagicMock()
        invitation.is_valid = False
        invitation.is_expired = True
        invitation.status = InvitationStatus.PENDING
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        with pytest.raises(ValueError, match="expired"):
            await service.accept("expired-token", user_id)

        invitation.mark_expired.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_raises_if_expired_already_marked(self, mock_db, make_result, user_id):
        invitation = MagicMock()
        invitation.is_valid = False
        invitation.is_expired = True
        invitation.status = InvitationStatus.EXPIRED
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        with pytest.raises(ValueError, match="expired"):
            await service.accept("expired-token", user_id)

        # Should NOT call mark_expired since already EXPIRED status
        invitation.mark_expired.assert_not_called()

    async def test_raises_if_not_valid_not_expired(self, mock_db, make_result, user_id):
        invitation = MagicMock()
        invitation.is_valid = False
        invitation.is_expired = False
        # Use a MagicMock for status that has a .value attribute
        mock_status = MagicMock()
        mock_status.value = "revoked"
        mock_status.__eq__ = lambda self, other: False  # not PENDING
        invitation.status = mock_status
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        with pytest.raises(ValueError, match="revoked"):
            await service.accept("revoked-token", user_id)

    async def test_accept_existing_collaborator(self, mock_db, make_result, user_id, collection_id):
        invitation = MagicMock()
        invitation.is_valid = True
        invitation.collection_id = collection_id
        invitation.permission = CollaboratorPermission.READ
        invitation.invited_by = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

        existing_collab = MagicMock()

        # Call sequence: get_by_token, collab_service.get (existing), flush, refresh
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=invitation),  # get_by_token
                make_result(scalar_one_or_none=existing_collab),  # collab_service.get
            ]
        )

        service = CollectionInvitationService(mock_db)
        result = await service.accept("valid-token", user_id)

        assert result is not None
        inv, collab = result
        assert inv is invitation
        assert collab is existing_collab
        invitation.accept.assert_called_once_with(user_id)

    async def test_accept_new_collaborator(self, mock_db, make_result, user_id, collection_id):
        invitation = MagicMock()
        invitation.is_valid = True
        invitation.collection_id = collection_id
        invitation.permission = CollaboratorPermission.WRITE
        invitation.invited_by = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

        # Call sequence:
        # 1. get_by_token -> invitation
        # 2. collab_service.get -> None (not existing collaborator)
        # 3. collab_service.add -> collab_service.get (check) -> None
        # 4. flush from collab_service.add
        # 5. refresh from collab_service.add
        # Then flush + refresh for invitation accept
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=invitation),  # get_by_token
                make_result(scalar_one_or_none=None),  # collab_service.get (no existing)
                make_result(scalar_one_or_none=None),  # collab_service.add -> get (check)
            ]
        )

        service = CollectionInvitationService(mock_db)
        result = await service.accept("valid-token", user_id)

        assert result is not None
        inv, collab = result
        assert inv is invitation
        invitation.accept.assert_called_once_with(user_id)


# ============================================================
# revoke
# ============================================================


class TestRevoke:
    async def test_revokes_pending(self, mock_db, make_result):
        invitation = MagicMock()
        invitation.status = InvitationStatus.PENDING
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        result = await service.revoke(inv_id)
        assert result is True
        invitation.revoke.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_returns_false_if_not_found(self, mock_db):
        service = CollectionInvitationService(mock_db)
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        result = await service.revoke(inv_id)
        assert result is False

    async def test_returns_false_if_not_pending(self, mock_db, make_result):
        invitation = MagicMock()
        invitation.status = InvitationStatus.ACCEPTED
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        result = await service.revoke(inv_id)
        assert result is False


# ============================================================
# revoke_by_token
# ============================================================


class TestRevokeByToken:
    async def test_revokes_pending(self, mock_db, make_result):
        invitation = MagicMock()
        invitation.status = InvitationStatus.PENDING
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        result = await service.revoke_by_token("test-token")
        assert result is True
        invitation.revoke.assert_called_once()

    async def test_returns_false_if_not_found(self, mock_db):
        service = CollectionInvitationService(mock_db)
        result = await service.revoke_by_token("nonexistent")
        assert result is False

    async def test_returns_false_if_not_pending(self, mock_db, make_result):
        invitation = MagicMock()
        invitation.status = InvitationStatus.EXPIRED
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        result = await service.revoke_by_token("test-token")
        assert result is False


# ============================================================
# expire_old_invitations
# ============================================================


class TestExpireOldInvitations:
    async def test_expires_invitations(self, mock_db, make_result):
        mock_db.execute = AsyncMock(return_value=make_result(rowcount=3))
        service = CollectionInvitationService(mock_db)
        result = await service.expire_old_invitations()
        assert result == 3
        mock_db.flush.assert_called_once()

    async def test_no_invitations_to_expire(self, mock_db):
        service = CollectionInvitationService(mock_db)
        result = await service.expire_old_invitations()
        assert result == 0


# ============================================================
# delete_old_invitations
# ============================================================


class TestDeleteOldInvitations:
    async def test_deletes_old(self, mock_db, make_result):
        mock_db.execute = AsyncMock(return_value=make_result(rowcount=5))
        service = CollectionInvitationService(mock_db)
        result = await service.delete_old_invitations(days=30)
        assert result == 5
        mock_db.flush.assert_called_once()

    async def test_no_old_to_delete(self, mock_db):
        service = CollectionInvitationService(mock_db)
        result = await service.delete_old_invitations()
        assert result == 0

    async def test_custom_days(self, mock_db, make_result):
        mock_db.execute = AsyncMock(return_value=make_result(rowcount=2))
        service = CollectionInvitationService(mock_db)
        result = await service.delete_old_invitations(days=60)
        assert result == 2


# ============================================================
# count_pending_for_collection
# ============================================================


class TestCountPendingForCollection:
    async def test_returns_count(self, mock_db, make_result, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=7))
        service = CollectionInvitationService(mock_db)
        result = await service.count_pending_for_collection(collection_id)
        assert result == 7

    async def test_returns_zero(self, mock_db, collection_id):
        service = CollectionInvitationService(mock_db)
        result = await service.count_pending_for_collection(collection_id)
        assert result == 0


# ============================================================
# resend
# ============================================================


class TestResend:
    @patch("knowledge.models.CollectionInvitation.default_expiry", return_value="2026-03-01")
    @patch("knowledge.models.CollectionInvitation.generate_token", return_value="new-token")
    async def test_resends_pending_invitation(
        self, _mock_token, _mock_expiry, mock_db, make_result
    ):
        invitation = MagicMock()
        invitation.status = InvitationStatus.PENDING
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        result = await service.resend(inv_id)

        assert result is invitation
        assert invitation.token == "new-token"
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_returns_none_if_not_found(self, mock_db):
        service = CollectionInvitationService(mock_db)
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        result = await service.resend(inv_id)
        assert result is None

    async def test_returns_none_if_not_pending(self, mock_db, make_result):
        invitation = MagicMock()
        invitation.status = InvitationStatus.ACCEPTED
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))

        service = CollectionInvitationService(mock_db)
        result = await service.resend(inv_id)
        assert result is None

    @patch("knowledge.models.CollectionInvitation.generate_token", return_value="new-token-2")
    async def test_resend_with_custom_expiry(self, _mock_token, mock_db, make_result):
        from datetime import UTC, datetime

        invitation = MagicMock()
        invitation.status = InvitationStatus.PENDING
        inv_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=invitation))
        custom_expiry = datetime(2027, 1, 1, tzinfo=UTC)

        service = CollectionInvitationService(mock_db)
        result = await service.resend(inv_id, new_expires_at=custom_expiry)

        assert result is invitation
        assert invitation.expires_at == custom_expiry
