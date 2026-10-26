# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.session — SessionRepository (100% mocked)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.session import SessionRepository

from tests.conftest import make_execute_result, make_session


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
    return SessionRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        sess = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=sess))

        result = await repo.find_by_id(db, sess.id)
        assert result is sess

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_token_hash ───────────────────────────────────────────────────────


class TestFindByTokenHash:
    @pytest.mark.asyncio
    async def test_found_active_only(self, db, repo):
        sess = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=sess))

        result = await repo.find_by_token_hash(db, "hash-1")
        assert result is sess

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_token_hash(db, "missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_include_inactive(self, db, repo):
        sess = make_session(revoked_at=datetime.now(UTC))
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=sess))

        result = await repo.find_by_token_hash(db, "hash-1", active_only=False)
        assert result is sess


# ── find_active_for_user ─────────────────────────────────────────────────────


class TestFindActiveForUser:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        sess = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=sess))

        result = await repo.find_active_for_user(db, sess.id, sess.user_id)
        assert result is sess

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_active_for_user(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── find_unrevoked_by_id ─────────────────────────────────────────────────────


class TestFindUnrevokedById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        sess = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=sess))

        result = await repo.find_unrevoked_by_id(db, sess.id)
        assert result is sess

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_unrevoked_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_id_with_user ─────────────────────────────────────────────────────


class TestFindByIdWithUser:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        sess = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=sess))

        result = await repo.find_by_id_with_user(db, sess.id)
        assert result is sess

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id_with_user(db, uuid.uuid4())
        assert result is None


# ── list ─────────────────────────────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, db, repo):
        sessions = [make_session(), make_session()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=2),
                make_list_result(sessions),
            ]
        )

        items, total = await repo.list(db, page=1, page_size=20)

        assert items == sessions
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

        items, total = await repo.list(db)

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_with_user_filter(self, db, repo):
        uid = uuid.uuid4()
        sessions = [make_session(user_id=uid)]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(sessions),
            ]
        )

        items, total = await repo.list(db, user_id=uid)

        assert items == sessions
        assert total == 1

    @pytest.mark.asyncio
    async def test_active_only(self, db, repo):
        sessions = [make_session()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(sessions),
            ]
        )

        items, total = await repo.list(db, active_only=True)

        assert items == sessions
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_user_eager_loaded(self, db, repo):
        sessions = [make_session()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(sessions),
            ]
        )

        items, total = await repo.list(db, with_user=True)

        assert items == sessions
        assert total == 1


# ── list_for_user / list_active_for_user / list_active / list_expired_before ─


class TestListForUser:
    @pytest.mark.asyncio
    async def test_default_active_only(self, db, repo):
        uid = uuid.uuid4()
        sessions = [make_session(user_id=uid)]
        db.execute = AsyncMock(return_value=make_list_result(sessions))

        result = await repo.list_for_user(db, uid)
        assert result == sessions

    @pytest.mark.asyncio
    async def test_include_inactive(self, db, repo):
        uid = uuid.uuid4()
        sessions = [make_session(user_id=uid, revoked_at=datetime.now(UTC))]
        db.execute = AsyncMock(return_value=make_list_result(sessions))

        result = await repo.list_for_user(db, uid, active_only=False)
        assert result == sessions

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_for_user(db, uuid.uuid4())
        assert result == []


class TestListActiveForUser:
    @pytest.mark.asyncio
    async def test_returns_sessions(self, db, repo):
        uid = uuid.uuid4()
        sessions = [make_session(user_id=uid)]
        db.execute = AsyncMock(return_value=make_list_result(sessions))

        result = await repo.list_active_for_user(db, uid)
        assert result == sessions

    @pytest.mark.asyncio
    async def test_excludes_one_by_id(self, db, repo):
        uid = uuid.uuid4()
        sessions = [make_session(user_id=uid)]
        db.execute = AsyncMock(return_value=make_list_result(sessions))

        result = await repo.list_active_for_user(db, uid, except_session_id=uuid.uuid4())
        assert result == sessions


class TestListActive:
    @pytest.mark.asyncio
    async def test_no_user_filter(self, db, repo):
        sessions = [make_session(), make_session()]
        db.execute = AsyncMock(return_value=make_list_result(sessions))

        result = await repo.list_active(db)
        assert result == sessions

    @pytest.mark.asyncio
    async def test_with_user_filter(self, db, repo):
        uid = uuid.uuid4()
        sessions = [make_session(user_id=uid)]
        db.execute = AsyncMock(return_value=make_list_result(sessions))

        result = await repo.list_active(db, user_id=uid)
        assert result == sessions


class TestListExpiredBefore:
    @pytest.mark.asyncio
    async def test_returns_expired(self, db, repo):
        cutoff = datetime.now(UTC)
        sessions = [make_session(expires_at=cutoff - timedelta(days=1))]
        db.execute = AsyncMock(return_value=make_list_result(sessions))

        result = await repo.list_expired_before(db, cutoff)
        assert result == sessions


# ── count_active_for_user ────────────────────────────────────────────────────


class TestCountActiveForUser:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=5))

        result = await repo.count_active_for_user(db, uuid.uuid4())
        assert result == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, db, repo):
        res = MagicMock()
        res.scalar.return_value = None
        db.execute = AsyncMock(return_value=res)

        result = await repo.count_active_for_user(db, uuid.uuid4())
        assert result == 0


# ── add / revoke / revoke_many / touch_expiry / delete ───────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        sess = make_session()

        await repo.add(db, sess)

        db.add.assert_called_once_with(sess)
        db.flush.assert_awaited_once()


class TestRevoke:
    @pytest.mark.asyncio
    async def test_sets_revoked_at_and_flushes(self, db, repo):
        sess = make_session(revoked_at=None)

        await repo.revoke(db, sess)

        assert sess.revoked_at is not None
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_provided_timestamp(self, db, repo):
        sess = make_session(revoked_at=None)
        ts = datetime.now(UTC) - timedelta(hours=1)

        await repo.revoke(db, sess, at=ts)

        assert sess.revoked_at == ts


class TestRevokeMany:
    @pytest.mark.asyncio
    async def test_revokes_all_and_flushes(self, db, repo):
        sessions = [make_session(revoked_at=None), make_session(revoked_at=None)]

        await repo.revoke_many(db, sessions)

        for s in sessions:
            assert s.revoked_at is not None
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_list_still_flushes(self, db, repo):
        await repo.revoke_many(db, [])

        db.flush.assert_awaited_once()


class TestTouchExpiry:
    @pytest.mark.asyncio
    async def test_sets_expires_and_flushes(self, db, repo):
        sess = make_session()
        new_expiry = datetime.now(UTC) + timedelta(days=30)

        await repo.touch_expiry(db, sess, new_expiry)

        assert sess.expires_at == new_expiry
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        sess = make_session()
        db.delete = AsyncMock()

        await repo.delete(db, sess)

        db.delete.assert_awaited_once_with(sess)


class TestFindByTokenHashWithUser:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        session = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=session))

        assert await repo.find_by_token_hash_with_user(db, "hash") is session
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_by_token_hash_with_user(db, "hash") is None


class TestCountActive:
    @pytest.mark.asyncio
    async def test_all_users(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=9))

        assert await repo.count_active(db) == 9

    @pytest.mark.asyncio
    async def test_scoped_to_user(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=2))

        assert await repo.count_active(db, user_id=uuid.uuid4()) == 2

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count_active(db) == 0
