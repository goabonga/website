# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for CollaboratorService: all CRUD and utility methods."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.models.enums import CollaboratorPermission
from knowledge.services.collaborators import CollaboratorService

# ============================================================
# list
# ============================================================


class TestList:
    async def test_returns_collaborators(self, mock_db, make_result, collection_id):
        collab1 = MagicMock()
        collab2 = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[collab1, collab2]))
        service = CollaboratorService(mock_db)
        result = await service.list(collection_id)
        assert len(result) == 2
        assert result[0] is collab1
        assert result[1] is collab2

    async def test_returns_empty(self, mock_db, collection_id):
        service = CollaboratorService(mock_db)
        result = await service.list(collection_id)
        assert result == []

    async def test_with_offset_and_limit(self, mock_db, make_result, collection_id):
        collab = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[collab]))
        service = CollaboratorService(mock_db)
        result = await service.list(collection_id, offset=5, limit=10)
        assert len(result) == 1


# ============================================================
# get
# ============================================================


class TestGet:
    async def test_found(self, mock_db, make_result, collection_id, user_id):
        collab = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))
        service = CollaboratorService(mock_db)
        result = await service.get(collection_id, user_id)
        assert result is collab

    async def test_not_found(self, mock_db, collection_id, user_id):
        service = CollaboratorService(mock_db)
        result = await service.get(collection_id, user_id)
        assert result is None


# ============================================================
# add
# ============================================================


class TestAdd:
    async def test_creates_collaborator(
        self, mock_db, make_result, collection_id, user_id, other_user_id
    ):
        # First call (get) returns None -> no existing collaborator
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))
        service = CollaboratorService(mock_db)
        await service.add(collection_id, user_id, CollaboratorPermission.READ, other_user_id)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        added = mock_db.add.call_args[0][0]
        assert added.collection_id == collection_id
        assert added.user_id == user_id
        assert added.permission == CollaboratorPermission.READ
        assert added.invited_by == other_user_id

    async def test_raises_if_already_collaborator(
        self, mock_db, make_result, collection_id, user_id, other_user_id
    ):
        existing = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing))
        service = CollaboratorService(mock_db)

        with pytest.raises(ValueError, match="already a collaborator"):
            await service.add(collection_id, user_id, CollaboratorPermission.READ, other_user_id)


# ============================================================
# update_permission
# ============================================================


class TestUpdatePermission:
    async def test_found_and_updated(self, mock_db, make_result, collection_id, user_id):
        collab = MagicMock()
        collab.permission = CollaboratorPermission.READ
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))
        service = CollaboratorService(mock_db)
        result = await service.update_permission(
            collection_id, user_id, CollaboratorPermission.WRITE
        )
        assert result is collab
        assert collab.permission == CollaboratorPermission.WRITE
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_not_found_returns_none(self, mock_db, collection_id, user_id):
        service = CollaboratorService(mock_db)
        result = await service.update_permission(
            collection_id, user_id, CollaboratorPermission.WRITE
        )
        assert result is None


# ============================================================
# remove
# ============================================================


class TestRemove:
    async def test_found_and_removed(self, mock_db, make_result, collection_id, user_id):
        collab = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))
        service = CollaboratorService(mock_db)
        result = await service.remove(collection_id, user_id)
        assert result is True
        mock_db.delete.assert_called_once_with(collab)
        mock_db.flush.assert_called_once()

    async def test_not_found_returns_false(self, mock_db, collection_id, user_id):
        service = CollaboratorService(mock_db)
        result = await service.remove(collection_id, user_id)
        assert result is False


# ============================================================
# count
# ============================================================


class TestCount:
    async def test_returns_count(self, mock_db, make_result, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=5))
        service = CollaboratorService(mock_db)
        result = await service.count(collection_id)
        assert result == 5

    async def test_returns_zero_when_none(self, mock_db, collection_id):
        service = CollaboratorService(mock_db)
        result = await service.count(collection_id)
        assert result == 0


# ============================================================
# get_user_collaborations
# ============================================================


class TestGetUserCollaborations:
    async def test_returns_collaborations(self, mock_db, make_result, user_id):
        collab1 = MagicMock()
        collab2 = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[collab1, collab2]))
        service = CollaboratorService(mock_db)
        result = await service.get_user_collaborations(user_id)
        assert len(result) == 2

    async def test_returns_empty(self, mock_db, user_id):
        service = CollaboratorService(mock_db)
        result = await service.get_user_collaborations(user_id)
        assert result == []

    async def test_with_offset_limit(self, mock_db, make_result, user_id):
        collab = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[collab]))
        service = CollaboratorService(mock_db)
        result = await service.get_user_collaborations(user_id, offset=10, limit=5)
        assert len(result) == 1


# ============================================================
# is_collaborator
# ============================================================


class TestIsCollaborator:
    async def test_is_collaborator_true(self, mock_db, make_result, collection_id, user_id):
        collab = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))
        service = CollaboratorService(mock_db)
        assert await service.is_collaborator(collection_id, user_id) is True

    async def test_is_collaborator_false(self, mock_db, collection_id, user_id):
        service = CollaboratorService(mock_db)
        assert await service.is_collaborator(collection_id, user_id) is False


# ============================================================
# get_permission
# ============================================================


class TestGetPermission:
    async def test_returns_permission(self, mock_db, make_result, collection_id, user_id):
        collab = MagicMock()
        collab.permission = CollaboratorPermission.ADMIN
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=collab))
        service = CollaboratorService(mock_db)
        result = await service.get_permission(collection_id, user_id)
        assert result == CollaboratorPermission.ADMIN

    async def test_returns_none_if_not_collaborator(self, mock_db, collection_id, user_id):
        service = CollaboratorService(mock_db)
        result = await service.get_permission(collection_id, user_id)
        assert result is None


# ============================================================
# remove_all_for_collection
# ============================================================


class TestRemoveAllForCollection:
    async def test_removes_all(self, mock_db, make_result, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(rowcount=3))
        service = CollaboratorService(mock_db)
        result = await service.remove_all_for_collection(collection_id)
        assert result == 3
        mock_db.flush.assert_called_once()

    async def test_removes_none(self, mock_db, collection_id):
        service = CollaboratorService(mock_db)
        result = await service.remove_all_for_collection(collection_id)
        assert result == 0


# ============================================================
# remove_user_from_all
# ============================================================


class TestRemoveUserFromAll:
    async def test_removes_all(self, mock_db, make_result, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(rowcount=5))
        service = CollaboratorService(mock_db)
        result = await service.remove_user_from_all(user_id)
        assert result == 5
        mock_db.flush.assert_called_once()

    async def test_removes_none(self, mock_db, user_id):
        service = CollaboratorService(mock_db)
        result = await service.remove_user_from_all(user_id)
        assert result == 0
