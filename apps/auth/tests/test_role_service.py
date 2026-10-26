# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.role — RoleService flows not covered by the route tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.services.role import RoleService


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def service(repo):
    return RoleService(repository=repo)


@pytest.fixture
def db():
    return AsyncMock()


def _make_scope(name="users:read"):
    scope = MagicMock()
    scope.id = uuid.uuid4()
    scope.name = name
    return scope


def _make_role(name="editor"):
    role = MagicMock()
    role.id = uuid.uuid4()
    role.name = name
    role.role_scopes = []
    return role


class TestCount:
    @pytest.mark.asyncio
    async def test_without_filter(self, db, repo, service):
        repo.count.return_value = 6

        assert await service.count(db) == 6
        repo.count.assert_awaited_once_with(db, is_system=None)

    @pytest.mark.asyncio
    async def test_with_is_system(self, db, repo, service):
        repo.count.return_value = 2

        assert await service.count(db, is_system=True) == 2
        repo.count.assert_awaited_once_with(db, is_system=True)


class TestListActiveScopes:
    @pytest.mark.asyncio
    async def test_public_proxy_delegates_to_repository(self, db, repo, service):
        scopes = [_make_scope(), _make_scope("users:write")]
        repo.list_active_scopes.return_value = scopes

        assert await service.list_active_scopes(db) == scopes
        repo.list_active_scopes.assert_awaited_once_with(db)


class TestCreateRole:
    @pytest.mark.asyncio
    async def test_duplicate_name_rejected(self, db, repo, service):
        repo.find_by_name.return_value = _make_role()

        with pytest.raises(ValueError, match="already exists"):
            await service.create_role(db, name="editor", description=None)

    @pytest.mark.asyncio
    async def test_creates_role_without_scopes(self, db, repo, service):
        repo.find_by_name.return_value = None

        role = await service.create_role(db, name="editor", description="Editors")

        assert role.name == "editor"
        assert role.is_system is False
        repo.add.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_role_with_scopes(self, db, repo, service):
        repo.find_by_name.return_value = None
        repo.find_scope_by_id = AsyncMock(return_value=_make_scope())
        service._get_scope_by_id = AsyncMock(return_value=_make_scope())
        scope_ids = [uuid.uuid4(), uuid.uuid4()]

        await service.create_role(db, name="editor", description=None, scope_ids=scope_ids)

        # One add for the role plus one per scope assignment.
        assert repo.add.await_count == 3
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_scope_rejected(self, db, repo, service):
        repo.find_by_name.return_value = None
        service._get_scope_by_id = AsyncMock(return_value=None)
        missing = uuid.uuid4()

        with pytest.raises(ValueError, match=f"Scope {missing} not found"):
            await service.create_role(db, name="editor", description=None, scope_ids=[missing])

        db.commit.assert_not_awaited()


class TestUpdateRole:
    @pytest.mark.asyncio
    async def test_rename_to_taken_name_rejected(self, db, repo, service):
        repo.find_by_name.return_value = _make_role("viewer")

        with pytest.raises(ValueError, match="already exists"):
            await service.update_role(db, _make_role("editor"), name="viewer")

    @pytest.mark.asyncio
    async def test_rename_applies(self, db, repo, service):
        repo.find_by_name.return_value = None
        role = _make_role("editor")

        result = await service.update_role(db, role, name="publisher")

        assert result.name == "publisher"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_description_only_update_skips_name_lookup(self, db, repo, service):
        role = _make_role("editor")

        await service.update_role(db, role, description="new description")

        assert role.description == "new description"
        repo.find_by_name.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_same_name_skips_duplicate_check(self, db, repo, service):
        role = _make_role("editor")

        await service.update_role(db, role, name="editor")

        repo.find_by_name.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_scope_ids_replace_existing_assignments(self, db, repo, service):
        role = _make_role()
        role.role_scopes = [MagicMock(), MagicMock()]
        service._get_scope_by_id = AsyncMock(return_value=_make_scope())

        await service.update_role(db, role, scope_ids=[uuid.uuid4()])

        assert repo.delete.await_count == 2
        db.flush.assert_awaited_once()
        repo.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_scope_ids_clears_assignments(self, db, repo, service):
        role = _make_role()
        role.role_scopes = [MagicMock()]
        service._get_scope_by_id = AsyncMock()

        await service.update_role(db, role, scope_ids=[])

        repo.delete.assert_awaited_once()
        repo.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_scope_rejected(self, db, repo, service):
        role = _make_role()
        service._get_scope_by_id = AsyncMock(return_value=None)
        missing = uuid.uuid4()

        with pytest.raises(ValueError, match=f"Scope {missing} not found"):
            await service.update_role(db, role, scope_ids=[missing])


class TestSeedDefaultRoles:
    @pytest.mark.asyncio
    async def test_skips_roles_that_already_exist(self, db, repo, service):
        repo.find_by_name.return_value = _make_role()

        assert await service.seed_default_roles(db) == []
        repo.add.assert_not_awaited()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_missing_roles_with_resolvable_scopes(self, db, repo, service):
        from auth.db.models.rbac import DEFAULT_ROLES

        repo.find_by_name.return_value = None
        service._get_scope_by_name = AsyncMock(return_value=_make_scope())

        created = await service.seed_default_roles(db)

        assert created == list(DEFAULT_ROLES)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unresolvable_scope_is_skipped(self, db, repo, service):
        from auth.db.models.rbac import DEFAULT_ROLES

        repo.find_by_name.return_value = None
        service._get_scope_by_name = AsyncMock(return_value=None)

        created = await service.seed_default_roles(db)

        assert created == list(DEFAULT_ROLES)
        # Only the Role rows were staged — no RoleScope rows.
        assert repo.add.await_count == len(DEFAULT_ROLES)
