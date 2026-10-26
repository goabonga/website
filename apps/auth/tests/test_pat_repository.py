# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.pat — PATRepository (100% mocked)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.pat import PATRepository

from tests.conftest import make_execute_result, make_personal_access_token


def make_list_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return PATRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        pat = make_personal_access_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await repo.find_by_id(db, pat.id)
        assert result is pat

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_id_and_user ──────────────────────────────────────────────────────


class TestFindByIdAndUser:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        user_id = uuid.uuid4()
        pat = make_personal_access_token(user_id=user_id)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await repo.find_by_id_and_user(db, pat.id, user_id)
        assert result is pat

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id_and_user(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── find_active_by_token_hash ────────────────────────────────────────────────


class TestFindActiveByTokenHash:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        pat = make_personal_access_token(token_hash="abc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await repo.find_active_by_token_hash(db, "abc", datetime.now(UTC))
        assert result is pat

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_active_by_token_hash(db, "missing", datetime.now(UTC))
        assert result is None


# ── list_by_user ─────────────────────────────────────────────────────────────


class TestListByUser:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, db, repo):
        user_id = uuid.uuid4()
        pats = [
            make_personal_access_token(user_id=user_id),
            make_personal_access_token(user_id=user_id),
        ]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=2),
                make_list_result(pats),
            ]
        )

        items, total = await repo.list_by_user(db, user_id)

        assert list(items) == pats
        assert total == 2
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list_by_user(db, uuid.uuid4())

        assert list(items) == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_include_revoked(self, db, repo):
        user_id = uuid.uuid4()
        pats = [
            make_personal_access_token(user_id=user_id, revoked_at=datetime.now(UTC)),
        ]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(pats),
            ]
        )

        items, total = await repo.list_by_user(db, user_id, include_revoked=True)

        assert list(items) == pats
        assert total == 1

    @pytest.mark.asyncio
    async def test_pagination(self, db, repo):
        user_id = uuid.uuid4()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=100),
                make_list_result([]),
            ]
        )

        items, total = await repo.list_by_user(db, user_id, offset=20, limit=10)

        assert list(items) == []
        assert total == 100


# ── list_all ─────────────────────────────────────────────────────────────────


class TestListAll:
    @pytest.mark.asyncio
    async def test_without_user_filter(self, db, repo):
        pats = [make_personal_access_token(), make_personal_access_token()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=2),
                make_list_result(pats),
            ]
        )

        items, total = await repo.list_all(db)

        assert list(items) == pats
        assert total == 2

    @pytest.mark.asyncio
    async def test_with_user_filter(self, db, repo):
        user_id = uuid.uuid4()
        pats = [make_personal_access_token(user_id=user_id)]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(pats),
            ]
        )

        items, total = await repo.list_all(db, user_id=user_id)

        assert list(items) == pats
        assert total == 1

    @pytest.mark.asyncio
    async def test_include_revoked(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list_all(db, include_revoked=True, offset=0, limit=5)

        assert list(items) == []
        assert total == 0


# ── list_active_by_user ──────────────────────────────────────────────────────


class TestListActiveByUser:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        user_id = uuid.uuid4()
        pats = [make_personal_access_token(user_id=user_id)]
        db.execute = AsyncMock(return_value=make_list_result(pats))

        result = await repo.list_active_by_user(db, user_id)

        assert list(result) == pats

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_active_by_user(db, uuid.uuid4())

        assert list(result) == []


# ── list_active ──────────────────────────────────────────────────────────────


class TestListActive:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        pats = [make_personal_access_token(), make_personal_access_token()]
        db.execute = AsyncMock(return_value=make_list_result(pats))

        result = await repo.list_active(db)

        assert list(result) == pats


# ── list_for_cleanup ─────────────────────────────────────────────────────────


class TestListForCleanup:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        now = datetime.now(UTC)
        pats = [make_personal_access_token()]
        db.execute = AsyncMock(return_value=make_list_result(pats))

        result = await repo.list_for_cleanup(
            db,
            expired_cutoff=now - timedelta(days=30),
            revoked_cutoff=now - timedelta(days=30),
        )

        assert list(result) == pats

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        now = datetime.now(UTC)
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_for_cleanup(
            db,
            expired_cutoff=now,
            revoked_cutoff=now,
        )

        assert list(result) == []


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        pat = make_personal_access_token()

        await repo.add(db, pat)

        db.add.assert_called_once_with(pat)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        pat = make_personal_access_token()
        db.delete = AsyncMock()

        await repo.delete(db, pat)

        db.delete.assert_awaited_once_with(pat)
