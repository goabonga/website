# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.scope — ScopeRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.scope import ScopeRepository

from tests.conftest import make_execute_result


def make_list_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def make_all_rows_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.all()`` returns ``rows`` (row tuples)."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def make_scope(
    name: str = "user:read", category: str = "user", is_active: bool = True
) -> MagicMock:
    """Create a mock Scope model."""
    scope = MagicMock()
    scope.id = uuid.uuid4()
    scope.name = name
    scope.category = category
    scope.resource = name.split(":", 1)[0] if ":" in name else name
    scope.action = name.split(":", 1)[1] if ":" in name else ""
    scope.is_active = is_active
    return scope


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return ScopeRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        scope = make_scope()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=scope))

        result = await repo.find_by_id(db, scope.id)
        assert result is scope

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_name ─────────────────────────────────────────────────────────────


class TestFindByName:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        scope = make_scope(name="user:read")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=scope))

        result = await repo.find_by_name(db, "user:read")
        assert result is scope

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_name(db, "missing:scope")
        assert result is None


# ── list ─────────────────────────────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, db, repo):
        scopes = [make_scope(), make_scope(), make_scope()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=3),
                make_list_result(scopes),
            ]
        )

        items, total = await repo.list(db, page=1, page_size=20)

        assert items == scopes
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
    async def test_pagination_offset_computed(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=100),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(db, page=3, page_size=20)

        assert items == []
        assert total == 100

    @pytest.mark.asyncio
    async def test_with_category_filter(self, db, repo):
        scopes = [make_scope(category="admin")]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(scopes),
            ]
        )

        items, total = await repo.list(db, category="admin")

        assert items == scopes
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_is_active_filter(self, db, repo):
        scopes = [make_scope(is_active=True)]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(scopes),
            ]
        )

        items, total = await repo.list(db, is_active=True)

        assert items == scopes
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_search(self, db, repo):
        scopes = [make_scope(name="user:read")]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(scopes),
            ]
        )

        items, total = await repo.list(db, search="user")

        assert items == scopes
        assert total == 1

    @pytest.mark.asyncio
    async def test_order_by_category_ascending(self, db, repo):
        scopes = [make_scope()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(scopes),
            ]
        )

        items, total = await repo.list(db, order_by_created_desc=False)

        assert items == scopes
        assert total == 1

    @pytest.mark.asyncio
    async def test_all_filters_combined(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(
            db,
            page=2,
            page_size=10,
            search="foo",
            category="billing",
            is_active=False,
            order_by_created_desc=False,
        )

        assert items == []
        assert total == 0


# ── list_distinct_categories ─────────────────────────────────────────────────


class TestListDistinctCategories:
    @pytest.mark.asyncio
    async def test_returns_categories(self, db, repo):
        rows = [("admin",), ("billing",), ("user",)]
        db.execute = AsyncMock(return_value=make_all_rows_result(rows))

        result = await repo.list_distinct_categories(db)

        assert result == ["admin", "billing", "user"]

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_all_rows_result([]))

        result = await repo.list_distinct_categories(db)

        assert result == []


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_to_session(self, db, repo):
        scope = make_scope()

        await repo.add(db, scope)

        db.add.assert_called_once_with(scope)


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        scope = make_scope()
        db.delete = AsyncMock()

        await repo.delete(db, scope)

        db.delete.assert_awaited_once_with(scope)


class TestListActiveRestrictedByNames:
    @pytest.mark.asyncio
    async def test_with_names_filter(self, db, repo):
        scopes = [make_scope()]
        db.execute = AsyncMock(return_value=make_list_result(scopes))

        assert await repo.list_active(db, names={"users:read"}) == scopes
        db.execute.assert_awaited_once()


class TestCountRolesForScope:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=5))

        assert await repo.count_roles_for_scope(db, uuid.uuid4()) == 5

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count_roles_for_scope(db, uuid.uuid4()) == 0


class TestListRolesForScope:
    @pytest.mark.asyncio
    async def test_returns_roles(self, db, repo):
        roles = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(roles))

        assert await repo.list_roles_for_scope(db, uuid.uuid4()) == roles

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_roles_for_scope(db, uuid.uuid4()) == []
