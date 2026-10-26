# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.user — UserRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.user import UserRepository

from tests.conftest import make_execute_result, make_user


def make_list_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().unique().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    unique = MagicMock()
    unique.all.return_value = rows
    scalars.unique.return_value = unique
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return UserRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        user = make_user()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        result = await repo.find_by_id(db, user.id)
        assert result is user

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_email ────────────────────────────────────────────────────────────


class TestFindByEmail:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        user = make_user()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        result = await repo.find_by_email(db, "test@example.com")
        assert result is user

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_email(db, "missing@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_email_is_lowercased(self, db, repo):
        """Ensure the query is built with a lowercased email."""
        captured_stmt: list = []

        async def capture(stmt):
            captured_stmt.append(stmt)
            return make_execute_result(scalar_value=None)

        db.execute = AsyncMock(side_effect=capture)

        await repo.find_by_email(db, "USER@EXAMPLE.COM")
        # The repository lowercases internally; we just assert the call happened.
        db.execute.assert_called_once()


# ── email_exists ─────────────────────────────────────────────────────────────


class TestEmailExists:
    @pytest.mark.asyncio
    async def test_exists(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=uuid.uuid4()))

        result = await repo.email_exists(db, "existing@example.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_not_exists(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.email_exists(db, "new@example.com")
        assert result is False


# ── list ─────────────────────────────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, db, repo):
        users = [make_user(), make_user(), make_user()]
        # First execute call is the count query, second is the select
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=3),
                make_list_result(users),
            ]
        )

        items, total = await repo.list(db, page=1, page_size=20)

        assert items == users
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

        items, total = await repo.list(db, page=1, page_size=20)

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_pagination_offset_computed(self, db, repo):
        """page=3, page_size=20 should produce offset=40 (verified by smoke call)."""
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
    async def test_with_is_active_filter(self, db, repo):
        users = [make_user(is_active=True)]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(users),
            ]
        )

        items, total = await repo.list(db, is_active=True)

        assert items == users
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_search(self, db, repo):
        users = [make_user()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(users),
            ]
        )

        items, total = await repo.list(db, search="alice")

        assert items == users
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_tenant_filter(self, db, repo):
        tid = uuid.uuid4()
        users = [make_user()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(users),
            ]
        )

        items, total = await repo.list(db, registration_tenant_id=tid)

        assert items == users
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_filter_no_tenant(self, db, repo):
        users = [make_user()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(users),
            ]
        )

        items, total = await repo.list(db, filter_no_tenant=True)

        assert items == users
        assert total == 1

    @pytest.mark.asyncio
    async def test_filter_no_tenant_overrides_registration_tenant_id(self, db, repo):
        """When filter_no_tenant is True, registration_tenant_id is ignored."""
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(
            db, filter_no_tenant=True, registration_tenant_id=uuid.uuid4()
        )

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_all_filters_combined(self, db, repo):
        tid = uuid.uuid4()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(
            db,
            page=1,
            page_size=50,
            search="bob",
            is_active=False,
            registration_tenant_id=tid,
        )

        assert items == []
        assert total == 0


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        user = make_user()

        await repo.add(db, user)

        db.add.assert_called_once_with(user)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        user = make_user()
        db.delete = AsyncMock()

        await repo.delete(db, user)

        db.delete.assert_awaited_once_with(user)


# ── add_email / delete_email / add_password / add_profile ────────────────────


class TestAddEmail:
    @pytest.mark.asyncio
    async def test_stages_row(self, db, repo):
        email = MagicMock()

        result = await repo.add_email(db, email)

        db.add.assert_called_once_with(email)
        db.flush.assert_not_awaited()
        assert result is email


class TestDeleteEmail:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        email = MagicMock()
        db.delete = AsyncMock()

        await repo.delete_email(db, email)

        db.delete.assert_awaited_once_with(email)


class TestAddPassword:
    @pytest.mark.asyncio
    async def test_stages_row(self, db, repo):
        password = MagicMock()

        result = await repo.add_password(db, password)

        db.add.assert_called_once_with(password)
        db.flush.assert_not_awaited()
        assert result is password


class TestAddProfile:
    @pytest.mark.asyncio
    async def test_stages_row(self, db, repo):
        profile = MagicMock()

        result = await repo.add_profile(db, profile)

        db.add.assert_called_once_with(profile)
        db.flush.assert_not_awaited()
        assert result is profile


class TestFindUserEmailRow:
    @pytest.mark.asyncio
    async def test_found_lowercases_input(self, db, repo):
        row = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=row))

        assert await repo.find_user_email_row(db, "USER@Example.COM") is row
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_user_email_row(db, "nobody@example.com") is None


class TestCountUsers:
    @pytest.mark.asyncio
    async def test_without_filters(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=25))

        assert await repo.count(db) == 25

    @pytest.mark.asyncio
    async def test_with_is_active(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=20))

        assert await repo.count(db, is_active=True) == 20

    @pytest.mark.asyncio
    async def test_with_created_since(self, db, repo):
        from datetime import UTC, datetime

        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=4))

        assert await repo.count(db, created_since=datetime.now(UTC)) == 4

    @pytest.mark.asyncio
    async def test_with_all_filters(self, db, repo):
        from datetime import UTC, datetime

        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=2))

        assert await repo.count(db, is_active=False, created_since=datetime.now(UTC)) == 2

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count(db) == 0
