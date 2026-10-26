# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for backend.session.service.SessionService."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.session.service import SessionService


@pytest.fixture
def mock_redis():
    """Return a mocked Redis client for SessionService tests."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.close = AsyncMock()
    return r


@pytest.fixture
def mock_db():
    """Return a mocked AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def service(mock_db, mock_redis):
    """Return a SessionService with mocked db and redis."""
    svc = SessionService(db=mock_db)
    svc._redis = mock_redis
    svc._get_redis = AsyncMock(return_value=mock_redis)
    return svc


class TestSessionServiceGet:
    """Tests for SessionService.get."""

    async def test_get_cache_hit_returns_cached_data(self, service, mock_redis):
        """When Redis has the session cached, return it directly."""
        session_id = "abcdef12-3456-7890-abcd-ef1234567890"
        cached_data = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "created_at": "2024-01-01T00:00:00+00:00",
            "last_active": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        result = await service.get(session_id)

        assert result == cached_data
        mock_redis.get.assert_awaited_once()
        mock_redis.expire.assert_awaited_once()

    async def test_get_cache_miss_db_hit_caches_and_returns(self, service, mock_redis, mock_db):
        """When Redis misses but DB has the session, cache it and return."""
        session_id = "abcdef12-3456-7890-abcd-ef1234567890"
        mock_redis.get.return_value = None

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session.session_id = session_id
        mock_session.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        mock_session.last_active = datetime(2024, 1, 1, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await service.get(session_id)

        assert result is not None
        assert result["session_id"] == session_id
        assert result["id"] == str(mock_session.id)
        mock_redis.setex.assert_awaited_once()

    async def test_get_not_found_anywhere_returns_none(self, service, mock_redis, mock_db):
        """When neither Redis nor DB has the session, return None."""
        session_id = "abcdef12-3456-7890-abcd-ef1234567890"
        mock_redis.get.return_value = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get(session_id)

        assert result is None


class TestSessionServiceCreate:
    """Tests for SessionService.create."""

    async def test_create_valid_uuid_creates_session_in_db_and_cache(
        self, service, mock_redis, mock_db
    ):
        """Creating a session with a valid UUID persists in DB and Redis."""
        session_id = str(uuid.uuid4())

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session.session_id = session_id
        mock_session.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        mock_session.last_active = datetime(2024, 1, 1, tzinfo=UTC)

        async def fake_refresh(obj):
            obj.id = mock_session.id
            obj.session_id = mock_session.session_id
            obj.created_at = mock_session.created_at
            obj.last_active = mock_session.last_active

        mock_db.refresh.side_effect = fake_refresh

        result = await service.create(session_id)

        assert result["session_id"] == session_id
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()
        mock_redis.setex.assert_awaited_once()

    async def test_create_invalid_uuid_raises_value_error(self, service):
        """Creating a session with an invalid UUID raises ValueError."""
        with pytest.raises(ValueError, match="Invalid session ID format"):
            await service.create("not-a-valid-uuid")


class TestSessionServiceGetOrCreate:
    """Tests for SessionService.get_or_create."""

    async def test_get_or_create_returns_existing(self, service, mock_redis):
        """When the session exists, return it without creating a new one."""
        session_id = str(uuid.uuid4())
        existing_data = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "created_at": "2024-01-01T00:00:00+00:00",
            "last_active": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(existing_data)

        result = await service.get_or_create(session_id)

        assert result == existing_data

    async def test_get_or_create_creates_new_when_not_found(self, service, mock_redis, mock_db):
        """When the session does not exist, create and return a new one."""
        session_id = str(uuid.uuid4())
        mock_redis.get.return_value = None

        # DB also returns nothing for get()
        mock_result_get = MagicMock()
        mock_result_get.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result_get

        # Setup refresh for create()
        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session.session_id = session_id
        mock_session.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        mock_session.last_active = datetime(2024, 1, 1, tzinfo=UTC)

        async def fake_refresh(obj):
            obj.id = mock_session.id
            obj.session_id = mock_session.session_id
            obj.created_at = mock_session.created_at
            obj.last_active = mock_session.last_active

        mock_db.refresh.side_effect = fake_refresh

        result = await service.get_or_create(session_id)

        assert result["session_id"] == session_id
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()


class TestSessionServiceDelete:
    """Tests for SessionService.delete."""

    async def test_delete_existing_session_returns_true(self, service, mock_redis, mock_db):
        """Deleting an existing session removes it from DB and cache."""
        session_id = "abcdef12-3456-7890-abcd-ef1234567890"

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await service.delete(session_id)

        assert result is True
        mock_db.delete.assert_awaited_once_with(mock_session)
        mock_db.commit.assert_awaited_once()
        mock_redis.delete.assert_awaited_once()

    async def test_delete_non_existing_session_returns_false(self, service, mock_redis, mock_db):
        """Deleting a non-existing session returns False."""
        session_id = "abcdef12-3456-7890-abcd-ef1234567890"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.delete(session_id)

        assert result is False
        mock_db.delete.assert_not_awaited()
        # Cache key is still deleted to be safe
        mock_redis.delete.assert_awaited_once()


class TestSessionServiceClose:
    """Tests for SessionService.close."""

    async def test_close_closes_redis(self, service, mock_redis):
        """Closing the service closes the Redis connection."""
        await service.close()

        mock_redis.close.assert_awaited_once()
        assert service._redis is None

    async def test_close_without_redis(self, mock_db):
        """Closing the service when no Redis connection was created does nothing."""
        svc = SessionService(db=mock_db)
        svc._redis = None

        await svc.close()

        assert svc._redis is None


class TestSessionServiceGetRedis:
    """Tests for SessionService._get_redis."""

    @patch("backend.session.service.redis.from_url")
    @patch("backend.session.service.settings")
    async def test_get_redis_creates_connection(self, mock_settings, mock_from_url, mock_db):
        """_get_redis() creates a Redis connection when none exists."""
        mock_settings.session_redis_url = "redis://localhost:6379/2"
        mock_redis_instance = AsyncMock()
        mock_from_url.return_value = mock_redis_instance

        svc = SessionService(db=mock_db)
        assert svc._redis is None

        result = await svc._get_redis()

        assert result is mock_redis_instance
        assert svc._redis is mock_redis_instance
        mock_from_url.assert_called_once_with(
            "redis://localhost:6379/2",
            encoding="utf-8",
            decode_responses=True,
        )

    async def test_get_redis_reuses_existing_connection(self, mock_db):
        """_get_redis() returns existing connection without creating a new one."""
        existing_redis = AsyncMock()
        svc = SessionService(db=mock_db)
        svc._redis = existing_redis

        result = await svc._get_redis()

        assert result is existing_redis
