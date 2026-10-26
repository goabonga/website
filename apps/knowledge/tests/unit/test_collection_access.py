# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for CollectionAccessService: permission resolution logic."""

from unittest.mock import AsyncMock, MagicMock

from knowledge.models.enums import CollaboratorPermission
from knowledge.services.collection_access import AccessLevel, CollectionAccessService

# ============================================================
# Access priority ordering (pure logic)
# ============================================================


class TestAccessPriority:
    def test_ordering(self):
        service = CollectionAccessService(MagicMock())
        levels = [
            AccessLevel.NONE,
            AccessLevel.READ,
            AccessLevel.WRITE,
            AccessLevel.ADMIN,
            AccessLevel.OWNER,
        ]
        for i in range(len(levels) - 1):
            assert service._access_priority(levels[i]) < service._access_priority(levels[i + 1])


# ============================================================
# get_access_level
# ============================================================


class TestGetAccessLevel:
    async def test_user_owns_personal_collection(self, mock_db, mock_collection, user_id):
        """User who owns a personal collection gets OWNER access."""
        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(user_id, mock_collection)
        assert level == AccessLevel.OWNER
        # No DB call needed for direct ownership
        mock_db.execute.assert_not_called()

    async def test_different_user_no_access_personal(self, mock_db, mock_collection, other_user_id):
        """Different user with no collaboration gets NONE."""
        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(other_user_id, mock_collection)
        assert level == AccessLevel.NONE

    async def test_org_collection_owner_role(
        self, mock_db, make_result, mock_org_collection, mock_org_member_owner, user_id
    ):
        """Org member with OWNER role gets OWNER access."""
        result_org = make_result(scalar_one_or_none=mock_org_member_owner)
        result_collab = make_result()  # No collaborator
        mock_db.execute = AsyncMock(side_effect=[result_org, result_collab])

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(user_id, mock_org_collection)
        assert level == AccessLevel.OWNER

    async def test_org_collection_admin_role(
        self, mock_db, make_result, mock_org_collection, mock_org_member_admin, user_id
    ):
        """Org member with ADMIN role gets ADMIN access."""
        result_org = make_result(scalar_one_or_none=mock_org_member_admin)
        result_collab = make_result()
        mock_db.execute = AsyncMock(side_effect=[result_org, result_collab])

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(user_id, mock_org_collection)
        assert level == AccessLevel.ADMIN

    async def test_org_collection_member_role(
        self, mock_db, make_result, mock_org_collection, mock_org_member, user_id
    ):
        """Org member with MEMBER role gets WRITE access."""
        result_org = make_result(scalar_one_or_none=mock_org_member)
        result_collab = make_result()
        mock_db.execute = AsyncMock(side_effect=[result_org, result_collab])

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(user_id, mock_org_collection)
        assert level == AccessLevel.WRITE

    async def test_org_collection_non_member(self, mock_db, mock_org_collection, other_user_id):
        """Non-member of org with no collaboration gets NONE."""
        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(other_user_id, mock_org_collection)
        assert level == AccessLevel.NONE

    async def test_collaborator_read(self, mock_db, make_result, mock_collection, other_user_id):
        """Collaborator with READ permission gets READ access."""
        collab = MagicMock()
        collab.permission = CollaboratorPermission.READ
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(other_user_id, mock_collection)
        assert level == AccessLevel.READ

    async def test_collaborator_write(self, mock_db, make_result, mock_collection, other_user_id):
        collab = MagicMock()
        collab.permission = CollaboratorPermission.WRITE
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(other_user_id, mock_collection)
        assert level == AccessLevel.WRITE

    async def test_collaborator_admin(self, mock_db, make_result, mock_collection, other_user_id):
        collab = MagicMock()
        collab.permission = CollaboratorPermission.ADMIN
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(other_user_id, mock_collection)
        assert level == AccessLevel.ADMIN

    async def test_org_member_plus_collab_takes_highest(
        self, mock_db, make_result, mock_org_collection, mock_org_member, user_id
    ):
        """Org MEMBER (WRITE) + collab ADMIN -> ADMIN."""
        collab = MagicMock()
        collab.permission = CollaboratorPermission.ADMIN
        result_org = make_result(scalar_one_or_none=mock_org_member)
        result_collab = make_result(scalar_one_or_none=collab)
        mock_db.execute = AsyncMock(side_effect=[result_org, result_collab])

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(user_id, mock_org_collection)
        assert level == AccessLevel.ADMIN

    async def test_org_admin_plus_collab_read_stays_admin(
        self, mock_db, make_result, mock_org_collection, mock_org_member_admin, user_id
    ):
        """Org ADMIN + collab READ -> ADMIN (org wins)."""
        collab = MagicMock()
        collab.permission = CollaboratorPermission.READ
        result_org = make_result(scalar_one_or_none=mock_org_member_admin)
        result_collab = make_result(scalar_one_or_none=collab)
        mock_db.execute = AsyncMock(side_effect=[result_org, result_collab])

        service = CollectionAccessService(mock_db)
        level = await service.get_access_level(user_id, mock_org_collection)
        assert level == AccessLevel.ADMIN


# ============================================================
# can_* permission checks
# ============================================================


class TestCanPermissions:
    async def test_can_read_with_read_access(self, mock_db, mock_collection, user_id):
        """Owner can always read."""
        service = CollectionAccessService(mock_db)
        assert await service.can_read(user_id, mock_collection) is True

    async def test_can_read_with_none_access(self, mock_db, mock_collection, other_user_id):
        """No access -> can_read=False."""
        service = CollectionAccessService(mock_db)
        assert await service.can_read(other_user_id, mock_collection) is False

    async def test_can_write_with_owner(self, mock_db, mock_collection, user_id):
        service = CollectionAccessService(mock_db)
        assert await service.can_write(user_id, mock_collection) is True

    async def test_can_write_with_read_only(
        self, mock_db, make_result, mock_collection, other_user_id
    ):
        collab = MagicMock()
        collab.permission = CollaboratorPermission.READ
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))

        service = CollectionAccessService(mock_db)
        assert await service.can_write(other_user_id, mock_collection) is False

    async def test_can_admin_with_owner(self, mock_db, mock_collection, user_id):
        service = CollectionAccessService(mock_db)
        assert await service.can_admin(user_id, mock_collection) is True

    async def test_can_admin_with_write(self, mock_db, make_result, mock_collection, other_user_id):
        collab = MagicMock()
        collab.permission = CollaboratorPermission.WRITE
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))

        service = CollectionAccessService(mock_db)
        assert await service.can_admin(other_user_id, mock_collection) is False

    async def test_can_delete_owner_only(self, mock_db, mock_collection, user_id, other_user_id):
        service = CollectionAccessService(mock_db)
        assert await service.can_delete(user_id, mock_collection) is True
        assert await service.can_delete(other_user_id, mock_collection) is False

    async def test_can_invite_delegates_to_can_admin(self, mock_db, mock_collection, user_id):
        service = CollectionAccessService(mock_db)
        assert await service.can_invite(user_id, mock_collection) is True


# ============================================================
# check_org_can_create_collection
# ============================================================


class TestCheckOrgCanCreateCollection:
    async def test_admin_can_create(
        self, mock_db, make_result, mock_org_member_admin, user_id, org_id
    ):
        mock_db.execute = AsyncMock(
            return_value=make_result(scalar_one_or_none=mock_org_member_admin)
        )
        service = CollectionAccessService(mock_db)
        assert await service.check_org_can_create_collection(user_id, org_id) is True

    async def test_non_member_cannot_create(self, mock_db, user_id, org_id):
        service = CollectionAccessService(mock_db)
        assert await service.check_org_can_create_collection(user_id, org_id) is False

    async def test_member_with_setting_true(
        self, mock_db, make_result, mock_org_member, user_id, org_id
    ):
        mock_org = MagicMock()
        mock_org.allow_member_create_collections = True
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_org_member),
                make_result(scalar_one_or_none=mock_org),
            ]
        )
        service = CollectionAccessService(mock_db)
        assert await service.check_org_can_create_collection(user_id, org_id) is True

    async def test_member_with_setting_false(
        self, mock_db, make_result, mock_org_member, user_id, org_id
    ):
        mock_org = MagicMock()
        mock_org.allow_member_create_collections = False
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_org_member),
                make_result(scalar_one_or_none=mock_org),
            ]
        )
        service = CollectionAccessService(mock_db)
        assert await service.check_org_can_create_collection(user_id, org_id) is False

    async def test_member_org_not_found_returns_false(
        self, mock_db, make_result, mock_org_member, user_id, org_id
    ):
        """Member exists but organization not found in DB -> False (line 255)."""
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_org_member),  # member found
                make_result(scalar_one_or_none=None),  # org not found
            ]
        )
        service = CollectionAccessService(mock_db)
        assert await service.check_org_can_create_collection(user_id, org_id) is False
