# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.role — RoleRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.role import RoleRepository

from tests.conftest import make_execute_result, make_user, make_user_email


def make_list_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def make_all_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.all()`` returns ``rows`` (tuple rows)."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def make_role(role_id=None, name="admin", is_system=False):
    """Create a mock Role model (local factory — Role is not in conftest)."""
    role = MagicMock()
    role.id = role_id or uuid.uuid4()
    role.name = name
    role.is_system = is_system
    return role


def make_role_scope(role_id=None, scope_id=None):
    """Create a mock RoleScope model."""
    rs = MagicMock()
    rs.id = uuid.uuid4()
    rs.role_id = role_id or uuid.uuid4()
    rs.scope_id = scope_id or uuid.uuid4()
    return rs


def make_user_role(role_id=None, user_id=None):
    """Create a mock UserRole model."""
    ur = MagicMock()
    ur.id = uuid.uuid4()
    ur.role_id = role_id or uuid.uuid4()
    ur.user_id = user_id or uuid.uuid4()
    return ur


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return RoleRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        role = make_role()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        result = await repo.find_by_id(db, role.id)
        assert result is role

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_load_scopes(self, db, repo):
        role = make_role()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        result = await repo.find_by_id(db, role.id, load_scopes=True)
        assert result is role
        db.execute.assert_awaited_once()


# ── find_by_name ─────────────────────────────────────────────────────────────


class TestFindByName:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        role = make_role(name="admin")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        result = await repo.find_by_name(db, "admin")
        assert result is role

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_name(db, "missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive(self, db, repo):
        role = make_role(name="admin")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        result = await repo.find_by_name(db, "ADMIN", case_insensitive=True)
        assert result is role


# ── list ─────────────────────────────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, db, repo):
        roles = [make_role(), make_role(), make_role()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=3),
                make_list_result(roles),
            ]
        )

        items, total = await repo.list(db)

        assert items == roles
        assert total == 3
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(db)

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_pagination(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=100),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(db, page=5, page_size=10)

        assert items == []
        assert total == 100

    @pytest.mark.asyncio
    async def test_search(self, db, repo):
        roles = [make_role(name="admin")]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(roles),
            ]
        )

        items, total = await repo.list(db, search="adm")

        assert items == roles
        assert total == 1

    @pytest.mark.asyncio
    async def test_is_system_filter(self, db, repo):
        roles = [make_role(is_system=True)]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(roles),
            ]
        )

        items, total = await repo.list(db, is_system=True)

        assert items == roles
        assert total == 1

    @pytest.mark.asyncio
    async def test_order_by_system_first(self, db, repo):
        roles = [make_role(is_system=True), make_role(is_system=False)]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=2),
                make_list_result(roles),
            ]
        )

        items, total = await repo.list(db, order_by_system_first=True)

        assert items == roles
        assert total == 2

    @pytest.mark.asyncio
    async def test_without_load_scopes(self, db, repo):
        roles = [make_role()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(roles),
            ]
        )

        items, total = await repo.list(db, load_scopes=False)

        assert items == roles
        assert total == 1


# ── count_users_for_role ─────────────────────────────────────────────────────


class TestCountUsersForRole:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=7))

        result = await repo.count_users_for_role(db, uuid.uuid4())
        assert result == 7

    @pytest.mark.asyncio
    async def test_zero(self, db, repo):
        # Explicitly set result.scalar() to None to exercise the `or 0` fallback.
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await repo.count_users_for_role(db, uuid.uuid4())
        assert result == 0


# ── list_users_for_role ──────────────────────────────────────────────────────


class TestListUsersForRole:
    @pytest.mark.asyncio
    async def test_returns_tuples(self, db, repo):
        role_id = uuid.uuid4()
        user = make_user()
        ur = make_user_role(role_id=role_id, user_id=user.id)
        email = make_user_email(user_id=user.id, user=user)
        rows = [(ur, user, email)]
        db.execute = AsyncMock(return_value=make_all_result(rows))

        result = await repo.list_users_for_role(db, role_id)

        assert result == rows

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_all_result([]))

        result = await repo.list_users_for_role(db, uuid.uuid4())

        assert result == []


# ── find_role_scope ──────────────────────────────────────────────────────────


class TestFindRoleScope:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        rs = make_role_scope()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=rs))

        result = await repo.find_role_scope(db, rs.role_id, rs.scope_id)
        assert result is rs

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_role_scope(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── find_user_role ───────────────────────────────────────────────────────────


class TestFindUserRole:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        ur = make_user_role()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ur))

        result = await repo.find_user_role(db, ur.role_id, ur.user_id)
        assert result is ur

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_user_role(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── list_user_roles_for_user ─────────────────────────────────────────────────


class TestListUserRolesForUser:
    @pytest.mark.asyncio
    async def test_returns_roles(self, db, repo):
        roles = [make_role(), make_role()]
        db.execute = AsyncMock(return_value=make_list_result(roles))

        result = await repo.list_user_roles_for_user(db, uuid.uuid4())

        assert result == roles

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_user_roles_for_user(db, uuid.uuid4())

        assert result == []


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_role_and_flushes(self, db, repo):
        role = make_role()

        await repo.add(db, role)

        db.add.assert_called_once_with(role)
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_adds_role_scope(self, db, repo):
        rs = make_role_scope()

        await repo.add(db, rs)

        db.add.assert_called_once_with(rs)
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_adds_user_role(self, db, repo):
        ur = make_user_role()

        await repo.add(db, ur)

        db.add.assert_called_once_with(ur)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_role(self, db, repo):
        role = make_role()
        db.delete = AsyncMock()

        await repo.delete(db, role)

        db.delete.assert_awaited_once_with(role)

    @pytest.mark.asyncio
    async def test_deletes_user_role(self, db, repo):
        ur = make_user_role()
        db.delete = AsyncMock()

        await repo.delete(db, ur)

        db.delete.assert_awaited_once_with(ur)


class TestCount:
    @pytest.mark.asyncio
    async def test_without_filter(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=6))

        assert await repo.count(db) == 6

    @pytest.mark.asyncio
    async def test_with_is_system(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=2))

        assert await repo.count(db, is_system=True) == 2

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count(db) == 0


class TestListUserRoleAssignmentsWithScopes:
    @pytest.mark.asyncio
    async def test_returns_assignments(self, db, repo):
        assignments = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(assignments))

        assert await repo.list_user_role_assignments_with_scopes(db, uuid.uuid4()) == assignments
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_user_role_assignments_with_scopes(db, uuid.uuid4()) == []


class TestListActiveScopes:
    @pytest.mark.asyncio
    async def test_returns_scopes(self, db, repo):
        scopes = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(scopes))

        assert await repo.list_active_scopes(db) == scopes

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_active_scopes(db) == []
