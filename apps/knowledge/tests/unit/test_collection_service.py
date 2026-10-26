# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for CollectionService: CRUD operations with mock DB."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from knowledge.models.enums import OwnerType
from knowledge.schemas.collection import CollectionCreate, CollectionUpdate
from knowledge.services.collections import CollectionService

# ============================================================
# create_for_owner
# ============================================================


class TestCreateForOwner:
    async def test_create_user_collection(self, mock_db, user_id):
        service = CollectionService(mock_db)
        data = CollectionCreate(name="My Collection", slug="my-collection")
        await service.create_for_owner(OwnerType.USER, user_id, data)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        added = mock_db.add.call_args[0][0]
        assert added.owner_type == OwnerType.USER
        assert added.owner_id == user_id
        assert added.organization_id is None
        assert added.name == "My Collection"
        assert added.slug == "my-collection"

    async def test_create_org_collection(self, mock_db, org_id):
        service = CollectionService(mock_db)
        data = CollectionCreate(name="Org Collection", slug="org-col")
        await service.create_for_owner(OwnerType.ORGANIZATION, org_id, data)

        added = mock_db.add.call_args[0][0]
        assert added.owner_type == OwnerType.ORGANIZATION
        assert added.organization_id == org_id


# ============================================================
# get_by_id_for_owner / get_by_slug_for_owner
# ============================================================


class TestGetByIdForOwner:
    async def test_found(self, mock_db, make_result, mock_collection, user_id, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_id_for_owner(OwnerType.USER, user_id, collection_id)
        assert result is mock_collection

    async def test_not_found(self, mock_db, user_id, collection_id):
        service = CollectionService(mock_db)
        result = await service.get_by_id_for_owner(OwnerType.USER, user_id, collection_id)
        assert result is None


class TestGetBySlugForOwner:
    async def test_found(self, mock_db, make_result, mock_collection, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_slug_for_owner(OwnerType.USER, user_id, "test-collection")
        assert result is mock_collection

    async def test_not_found(self, mock_db, user_id):
        service = CollectionService(mock_db)
        result = await service.get_by_slug_for_owner(OwnerType.USER, user_id, "nonexistent")
        assert result is None


# ============================================================
# get_by_id_or_slug_for_owner (dispatch logic)
# ============================================================


class TestGetByIdOrSlugForOwner:
    async def test_uuid_dispatches_to_get_by_id(
        self, mock_db, make_result, mock_collection, user_id, collection_id
    ):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_id_or_slug_for_owner(
            OwnerType.USER, user_id, str(collection_id)
        )
        assert result is mock_collection

    async def test_slug_dispatches_to_get_by_slug(
        self, mock_db, make_result, mock_collection, user_id
    ):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_id_or_slug_for_owner(OwnerType.USER, user_id, "my-slug")
        assert result is mock_collection


# ============================================================
# list_for_owner
# ============================================================


class TestListForOwner:
    async def test_returns_results(self, mock_db, make_result, mock_collection, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[mock_collection]))
        service = CollectionService(mock_db)
        result = await service.list_for_owner(OwnerType.USER, user_id)
        assert len(result) == 1
        assert result[0] is mock_collection

    async def test_returns_empty(self, mock_db, user_id):
        service = CollectionService(mock_db)
        result = await service.list_for_owner(OwnerType.USER, user_id)
        assert result == []


# ============================================================
# slug_exists_for_owner
# ============================================================


class TestSlugExistsForOwner:
    async def test_exists(self, mock_db, make_result, user_id, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collection_id))
        service = CollectionService(mock_db)
        assert await service.slug_exists_for_owner(OwnerType.USER, user_id, "test") is True

    async def test_not_exists(self, mock_db, user_id):
        service = CollectionService(mock_db)
        assert await service.slug_exists_for_owner(OwnerType.USER, user_id, "test") is False


# ============================================================
# update_for_owner
# ============================================================


class TestUpdateForOwner:
    async def test_found_and_updated(
        self, mock_db, make_result, mock_collection, user_id, collection_id
    ):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        data = CollectionUpdate(name="Updated Name")
        result = await service.update_for_owner(OwnerType.USER, user_id, collection_id, data)

        assert result is mock_collection
        assert mock_collection.name == "Updated Name"
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_not_found_returns_none(self, mock_db, user_id, collection_id):
        service = CollectionService(mock_db)
        data = CollectionUpdate(name="Updated")
        result = await service.update_for_owner(OwnerType.USER, user_id, collection_id, data)
        assert result is None


# ============================================================
# delete_for_owner
# ============================================================


class TestDeleteForOwner:
    async def test_found_and_deleted(
        self, mock_db, make_result, mock_collection, user_id, collection_id
    ):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.delete_for_owner(OwnerType.USER, user_id, collection_id)

        assert result is True
        mock_db.delete.assert_called_once_with(mock_collection)

    async def test_not_found_returns_false(self, mock_db, user_id, collection_id):
        service = CollectionService(mock_db)
        result = await service.delete_for_owner(OwnerType.USER, user_id, collection_id)
        assert result is False


# ============================================================
# increment_document_count
# ============================================================


class TestIncrementDocumentCount:
    async def test_increments_existing(self, mock_db, make_result, mock_collection, collection_id):
        mock_collection.document_count = 5
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        await service.increment_document_count(collection_id, 3)

        assert mock_collection.document_count == 8
        mock_db.flush.assert_called_once()

    async def test_decrements_existing(self, mock_db, make_result, mock_collection, collection_id):
        mock_collection.document_count = 5
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        await service.increment_document_count(collection_id, -2)
        assert mock_collection.document_count == 3

    async def test_not_found_no_op(self, mock_db, collection_id):
        service = CollectionService(mock_db)
        await service.increment_document_count(collection_id, 1)
        mock_db.flush.assert_not_called()


# ============================================================
# count_for_owner
# ============================================================


class TestCountForOwner:
    async def test_returns_count(self, mock_db, make_result, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=7))
        service = CollectionService(mock_db)
        count = await service.count_for_owner(OwnerType.USER, user_id)
        assert count == 7

    async def test_returns_zero(self, mock_db, user_id):
        service = CollectionService(mock_db)
        count = await service.count_for_owner(OwnerType.USER, user_id)
        assert count == 0


# ============================================================
# list_accessible (lines 194-246)
# ============================================================


class TestListAccessible:
    async def test_all_access_types(self, mock_db, make_result, mock_collection, user_id):
        """With all include flags true, returns collections."""
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[mock_collection]))
        service = CollectionService(mock_db)
        result = await service.list_accessible(user_id)
        assert len(result) == 1

    async def test_only_owned(self, mock_db, make_result, mock_collection, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[mock_collection]))
        service = CollectionService(mock_db)
        result = await service.list_accessible(
            user_id,
            include_owned=True,
            include_collaborated=False,
            include_organization=False,
        )
        assert len(result) == 1

    async def test_only_collaborated(self, mock_db, make_result, mock_collection, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[mock_collection]))
        service = CollectionService(mock_db)
        result = await service.list_accessible(
            user_id,
            include_owned=False,
            include_collaborated=True,
            include_organization=False,
        )
        assert len(result) == 1

    async def test_only_organization(self, mock_db, make_result, mock_collection, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[mock_collection]))
        service = CollectionService(mock_db)
        result = await service.list_accessible(
            user_id,
            include_owned=False,
            include_collaborated=False,
            include_organization=True,
        )
        assert len(result) == 1

    async def test_with_organization_id_filter(
        self, mock_db, make_result, mock_collection, user_id, org_id
    ):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[mock_collection]))
        service = CollectionService(mock_db)
        result = await service.list_accessible(
            user_id,
            include_owned=False,
            include_collaborated=False,
            include_organization=True,
            organization_id=org_id,
        )
        assert len(result) == 1

    async def test_no_conditions_returns_empty(self, mock_db, user_id):
        service = CollectionService(mock_db)
        result = await service.list_accessible(
            user_id,
            include_owned=False,
            include_collaborated=False,
            include_organization=False,
        )
        assert result == []

    async def test_with_offset_limit(self, mock_db, make_result, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[]))
        service = CollectionService(mock_db)
        result = await service.list_accessible(user_id, offset=5, limit=10)
        assert result == []


# ============================================================
# get_accessible (lines 265-298)
# ============================================================


class TestGetAccessible:
    async def test_not_found(self, mock_db, user_id, collection_id):
        """Collection doesn't exist -> None."""
        service = CollectionService(mock_db)
        result = await service.get_accessible(user_id, collection_id)
        assert result is None

    async def test_user_owns_collection(self, mock_db, make_result, user_id, collection_id):
        """User owns the collection -> returns it."""
        mock_coll = MagicMock()
        mock_coll.owner_type = OwnerType.USER
        mock_coll.owner_id = user_id
        mock_coll.collaborators = []
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_coll))
        service = CollectionService(mock_db)
        result = await service.get_accessible(user_id, collection_id)
        assert result is mock_coll

    async def test_user_is_collaborator(
        self, mock_db, make_result, other_user_id, collection_id, user_id
    ):
        """User is a collaborator on the collection -> returns it."""
        collab = MagicMock()
        collab.user_id = other_user_id
        mock_coll = MagicMock()
        mock_coll.owner_type = OwnerType.USER
        mock_coll.owner_id = user_id  # owned by someone else but we check other_user_id
        mock_coll.collaborators = [collab]
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_coll))
        service = CollectionService(mock_db)
        result = await service.get_accessible(other_user_id, collection_id)
        assert result is mock_coll

    async def test_user_in_organization(
        self, mock_db, make_result, other_user_id, collection_id, org_id
    ):
        """User is in the organization that owns the collection -> returns it."""
        mock_coll = MagicMock()
        mock_coll.owner_type = OwnerType.ORGANIZATION
        mock_coll.owner_id = org_id
        mock_coll.collaborators = []

        mock_org_member = MagicMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_coll),  # get collection
                make_result(scalar_one_or_none=mock_org_member),  # org membership check
            ]
        )
        service = CollectionService(mock_db)
        result = await service.get_accessible(other_user_id, collection_id)
        assert result is mock_coll

    async def test_user_not_in_organization(
        self, mock_db, make_result, other_user_id, collection_id, org_id
    ):
        """User is NOT in the org and NOT a collaborator -> None."""
        mock_coll = MagicMock()
        mock_coll.owner_type = OwnerType.ORGANIZATION
        mock_coll.owner_id = org_id
        mock_coll.collaborators = []

        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_coll),  # get collection
                make_result(scalar_one_or_none=None),  # org membership -> None
            ]
        )
        service = CollectionService(mock_db)
        result = await service.get_accessible(other_user_id, collection_id)
        assert result is None

    async def test_collaborator_no_match(
        self, mock_db, make_result, other_user_id, collection_id, org_id
    ):
        """Collaborators exist but none match the user (branch 284->283)."""
        wrong_collab = MagicMock()
        wrong_collab.user_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        mock_coll = MagicMock()
        mock_coll.owner_type = OwnerType.ORGANIZATION
        mock_coll.owner_id = org_id
        mock_coll.collaborators = [wrong_collab]

        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_coll),  # get collection
                make_result(scalar_one_or_none=None),  # org membership -> None
            ]
        )
        service = CollectionService(mock_db)
        result = await service.get_accessible(other_user_id, collection_id)
        assert result is None

    async def test_user_owned_not_owner_no_collab(
        self, mock_db, make_result, other_user_id, collection_id, user_id
    ):
        """USER-owned collection but user is not owner and not collaborator (branch 288->298)."""
        mock_coll = MagicMock()
        mock_coll.owner_type = OwnerType.USER
        mock_coll.owner_id = user_id  # owned by user_id, not other_user_id
        mock_coll.collaborators = []

        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_coll))
        service = CollectionService(mock_db)
        result = await service.get_accessible(other_user_id, collection_id)
        assert result is None


# ============================================================
# Legacy methods (lines 390, 402, 414, 426, 444, 462, 474)
# ============================================================


class TestLegacyCreate:
    async def test_delegates_to_create_for_owner(self, mock_db, tenant_id):
        service = CollectionService(mock_db)
        data = CollectionCreate(name="Legacy Collection", slug="legacy-col")
        await service.create(tenant_id, data)
        mock_db.add.assert_called_once()
        added = mock_db.add.call_args[0][0]
        assert added.owner_type == OwnerType.ORGANIZATION
        assert added.owner_id == tenant_id


class TestLegacyGetById:
    async def test_delegates(self, mock_db, make_result, mock_collection, tenant_id, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_id(tenant_id, collection_id)
        assert result is mock_collection


class TestLegacyGetBySlug:
    async def test_delegates(self, mock_db, make_result, mock_collection, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_slug(tenant_id, "test-slug")
        assert result is mock_collection


class TestLegacyGetByIdOrSlug:
    async def test_delegates_with_uuid(
        self, mock_db, make_result, mock_collection, tenant_id, collection_id
    ):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_id_or_slug(tenant_id, str(collection_id))
        assert result is mock_collection

    async def test_delegates_with_slug(self, mock_db, make_result, mock_collection, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_id_or_slug(tenant_id, "my-slug")
        assert result is mock_collection


class TestLegacyList:
    async def test_delegates(self, mock_db, make_result, mock_collection, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[mock_collection]))
        service = CollectionService(mock_db)
        result = await service.list(tenant_id)
        assert len(result) == 1


class TestLegacyUpdate:
    async def test_delegates(self, mock_db, make_result, mock_collection, tenant_id, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        data = CollectionUpdate(name="Updated")
        result = await service.update(tenant_id, collection_id, data)
        assert result is mock_collection


class TestLegacyDelete:
    async def test_delegates(self, mock_db, make_result, mock_collection, tenant_id, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.delete(tenant_id, collection_id)
        assert result is True


# ============================================================
# get_by_id_global (lines 503-504)
# ============================================================


class TestGetByIdGlobal:
    async def test_found(self, mock_db, make_result, mock_collection, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_collection))
        service = CollectionService(mock_db)
        result = await service.get_by_id_global(collection_id)
        assert result is mock_collection

    async def test_not_found(self, mock_db, collection_id):
        service = CollectionService(mock_db)
        result = await service.get_by_id_global(collection_id)
        assert result is None


# ============================================================
# slug_exists_for_owner with exclude_id (line 531)
# ============================================================


class TestSlugExistsWithExclude:
    async def test_with_exclude_id(self, mock_db, make_result, user_id, collection_id):
        exclude = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collection_id))
        service = CollectionService(mock_db)
        result = await service.slug_exists_for_owner(
            OwnerType.USER, user_id, "test-slug", exclude_id=exclude
        )
        assert result is True

    async def test_with_exclude_id_not_found(self, mock_db, user_id):
        exclude = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        service = CollectionService(mock_db)
        result = await service.slug_exists_for_owner(
            OwnerType.USER, user_id, "test-slug", exclude_id=exclude
        )
        assert result is False
