# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.tenant_role — TenantRoleRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.tenant_role import TenantRoleRepository

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return TenantRoleRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        role = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is role

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_name_in_tenant ───────────────────────────────────────────────────


class TestFindByNameInTenant:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        role = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        result = await repo.find_by_name_in_tenant(db, uuid.uuid4(), "admin")
        assert result is role

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_name_in_tenant(db, uuid.uuid4(), "ghost")
        assert result is None


# ── list_roles_for_tenant ────────────────────────────────────────────────────


class TestListRolesForTenant:
    @pytest.mark.asyncio
    async def test_returns_roles(self, db, repo):
        roles = [MagicMock(), MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=roles))

        result = await repo.list_roles_for_tenant(db, uuid.uuid4())
        assert result == roles

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        result = await repo.list_roles_for_tenant(db, uuid.uuid4())
        assert result == []


# ── find_default_role ────────────────────────────────────────────────────────


class TestFindDefaultRole:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        role = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        result = await repo.find_default_role(db, uuid.uuid4())
        assert result is role

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_default_role(db, uuid.uuid4())
        assert result is None


# ── max_display_order ────────────────────────────────────────────────────────


class TestMaxDisplayOrder:
    @pytest.mark.asyncio
    async def test_returns_max(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=7))

        result = await repo.max_display_order(db, uuid.uuid4())
        assert result == 7

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, db, repo):
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.max_display_order(db, uuid.uuid4())
        assert result == 0


# ── count_members_for_role ───────────────────────────────────────────────────


class TestCountMembersForRole:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=4))

        result = await repo.count_members_for_role(db, uuid.uuid4())
        assert result == 4

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, db, repo):
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.count_members_for_role(db, uuid.uuid4())
        assert result == 0


# ── list_active_scope_names ──────────────────────────────────────────────────


class TestListActiveScopeNames:
    @pytest.mark.asyncio
    async def test_returns_set(self, db, repo):
        db.execute = AsyncMock(
            return_value=make_execute_result(all_rows=[("scope:a",), ("scope:b",)])
        )

        result = await repo.list_active_scope_names(db)
        assert result == {"scope:a", "scope:b"}

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(all_rows=[]))

        result = await repo.list_active_scope_names(db)
        assert result == set()


# ── add / delete / flush ─────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        role = MagicMock()

        await repo.add(db, role)

        db.add.assert_called_once_with(role)
        db.flush.assert_awaited_once()


class TestStage:
    @pytest.mark.asyncio
    async def test_stages_without_flush(self, db, repo):
        role = MagicMock()

        result = await repo.stage(db, role)

        db.add.assert_called_once_with(role)
        db.flush.assert_not_awaited()
        assert result is role


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        role = MagicMock()
        db.delete = AsyncMock()

        await repo.delete(db, role)

        db.delete.assert_awaited_once_with(role)


class TestFlush:
    @pytest.mark.asyncio
    async def test_flushes(self, db, repo):
        await repo.flush(db)
        db.flush.assert_awaited_once()


# ── clear_default_flag ───────────────────────────────────────────────────────


class TestClearDefaultFlag:
    @pytest.mark.asyncio
    async def test_clears_all(self, db, repo):
        db.execute = AsyncMock()

        await repo.clear_default_flag(db, uuid.uuid4())

        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clears_except_target(self, db, repo):
        db.execute = AsyncMock()

        await repo.clear_default_flag(db, uuid.uuid4(), except_role_id=uuid.uuid4())

        db.execute.assert_awaited_once()


# ── sync helpers ─────────────────────────────────────────────────────────────


class TestListTenantRefs:
    @pytest.mark.asyncio
    async def test_returns_id_and_slug_pairs(self, db, repo):
        first, second = MagicMock(slug="acme"), MagicMock(slug="beta")
        first.id, second.id = uuid.uuid4(), uuid.uuid4()
        result = MagicMock()
        result.all.return_value = [first, second]
        db.execute = AsyncMock(return_value=result)

        assert await repo.list_tenant_refs(db) == [(first.id, "acme"), (second.id, "beta")]
        assert "ORDER BY tenants.slug" in str(db.execute.await_args.args[0])


class TestListRolesNamed:
    @pytest.mark.asyncio
    async def test_returns_the_roles_of_every_tenant(self, db, repo):
        roles = [MagicMock(), MagicMock()]
        result = MagicMock()
        result.scalars.return_value.all.return_value = roles
        db.execute = AsyncMock(return_value=result)

        assert await repo.list_roles_named(db, ["owner", "admin"]) == roles
        assert "tenant_roles.name IN" in str(db.execute.await_args.args[0])


class TestListTenantIdsWithDefaultRole:
    @pytest.mark.asyncio
    async def test_returns_a_set_of_tenant_ids(self, db, repo):
        tenant = uuid.uuid4()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [tenant, tenant]
        db.execute = AsyncMock(return_value=result)

        assert await repo.list_tenant_ids_with_default_role(db) == {tenant}
