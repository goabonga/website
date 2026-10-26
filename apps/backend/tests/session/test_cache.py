# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for backend.session.cache.ConversationCache."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.session.cache import ConversationCache


@pytest.fixture
def mock_redis():
    """Return a mocked Redis client for ConversationCache tests."""
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
def cache(mock_db, mock_redis):
    """Return a ConversationCache with mocked db and redis."""
    c = ConversationCache(db=mock_db)
    c._redis = mock_redis
    c._get_redis = AsyncMock(return_value=mock_redis)
    return c


@pytest.fixture
def conversation_id():
    """Return a fixed conversation UUID."""
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def sample_conv_data(conversation_id):
    """Return sample conversation data as stored in Redis."""
    return {
        "id": str(conversation_id),
        "user_id": str(uuid.UUID("12345678-1234-5678-1234-567812345678")),
        "session_id": None,
        "title": "Test Conversation",
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": "Hello",
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        ],
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }


class TestConversationCacheGet:
    """Tests for ConversationCache.get."""

    async def test_get_cache_hit_returns_data(
        self, cache, mock_redis, conversation_id, sample_conv_data
    ):
        """When Redis has the conversation cached, return it directly."""
        mock_redis.get.return_value = json.dumps(sample_conv_data)

        result = await cache.get(conversation_id)

        assert result == sample_conv_data
        mock_redis.get.assert_awaited_once()
        mock_redis.expire.assert_awaited_once()

    async def test_get_cache_miss_db_hit_caches_and_returns(
        self, cache, mock_redis, mock_db, conversation_id
    ):
        """When Redis misses but DB has the conversation, cache and return."""
        mock_redis.get.return_value = None

        mock_conv = MagicMock()
        mock_conv.id = conversation_id
        mock_conv.user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        mock_conv.session_id = None
        mock_conv.title = "Test Conversation"
        mock_conv.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        mock_conv.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
        mock_conv.messages = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conv
        mock_db.execute.return_value = mock_result

        result = await cache.get(conversation_id)

        assert result is not None
        assert result["id"] == str(conversation_id)
        assert result["title"] == "Test Conversation"
        mock_redis.setex.assert_awaited_once()

    async def test_get_not_found_returns_none(self, cache, mock_redis, mock_db, conversation_id):
        """When neither Redis nor DB has the conversation, return None."""
        mock_redis.get.return_value = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await cache.get(conversation_id)

        assert result is None


class TestConversationCacheAddMessage:
    """Tests for ConversationCache.add_message."""

    async def test_add_message_appends_and_marks_dirty(
        self, cache, mock_redis, conversation_id, sample_conv_data
    ):
        """Adding a message appends to conversation and sets dirty flag."""
        # Cache.get will be called internally; simulate a cache hit
        mock_redis.get.return_value = json.dumps(sample_conv_data)

        result = await cache.add_message(conversation_id, "assistant", "Hi there!")

        assert result["role"] == "assistant"
        assert result["content"] == "Hi there!"
        assert "id" in result
        assert "created_at" in result

        # Should write back updated conversation to cache
        mock_redis.setex.assert_awaited()

        # Should set dirty flag
        mock_redis.set.assert_awaited()
        dirty_call_args = mock_redis.set.call_args
        assert "dirty" in dirty_call_args[0][0]
        assert dirty_call_args[0][1] == "1"

    async def test_add_message_raises_value_error_if_not_found(
        self, cache, mock_redis, mock_db, conversation_id
    ):
        """Adding a message to a non-existing conversation raises ValueError."""
        mock_redis.get.return_value = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Conversation not found"):
            await cache.add_message(conversation_id, "user", "Hello")


class TestConversationCacheUpdateTitle:
    """Tests for ConversationCache.update_title."""

    async def test_update_title_updates_and_marks_dirty(
        self, cache, mock_redis, conversation_id, sample_conv_data
    ):
        """Updating title modifies cached data and sets dirty flag."""
        mock_redis.get.return_value = json.dumps(sample_conv_data)

        result = await cache.update_title(conversation_id, "New Title")

        assert result is not None
        assert result["title"] == "New Title"
        mock_redis.setex.assert_awaited()
        mock_redis.set.assert_awaited()

    async def test_update_title_returns_none_if_not_found(
        self, cache, mock_redis, mock_db, conversation_id
    ):
        """Updating title on a non-existing conversation returns None."""
        mock_redis.get.return_value = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await cache.update_title(conversation_id, "New Title")

        assert result is None


class TestConversationCacheGetDirtyConversations:
    """Tests for ConversationCache.get_dirty_conversations."""

    async def test_get_dirty_conversations_scans_redis_keys(self, cache, mock_redis):
        """Scanning dirty keys returns list of conversation IDs."""
        conv_id_1 = str(uuid.uuid4())
        conv_id_2 = str(uuid.uuid4())

        dirty_keys = [
            f"conv:dirty:{conv_id_1}",
            f"conv:dirty:{conv_id_2}",
        ]

        # Mock scan_iter as an async generator
        async def fake_scan_iter(pattern):
            for key in dirty_keys:
                yield key

        mock_redis.scan_iter = fake_scan_iter

        result = await cache.get_dirty_conversations()

        assert len(result) == 2
        assert conv_id_1 in result
        assert conv_id_2 in result


class TestConversationCacheDelete:
    """Tests for ConversationCache.delete."""

    async def test_delete_removes_from_db_and_cache(
        self, cache, mock_redis, mock_db, conversation_id
    ):
        """Deleting a conversation removes it from both DB and Redis."""
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conv
        mock_db.execute.return_value = mock_result

        result = await cache.delete(conversation_id)

        assert result is True
        mock_db.delete.assert_awaited_once_with(mock_conv)
        mock_db.commit.assert_awaited_once()
        mock_redis.delete.assert_awaited_once()

    async def test_delete_not_found_returns_false(
        self, cache, mock_redis, mock_db, conversation_id
    ):
        """Deleting a non-existing conversation returns False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await cache.delete(conversation_id)

        assert result is False
        mock_db.delete.assert_not_awaited()
        # Cache keys are still cleaned up
        mock_redis.delete.assert_awaited_once()


class TestConversationCacheInvalidate:
    """Tests for ConversationCache.invalidate."""

    async def test_invalidate_only_deletes_from_redis(
        self, cache, mock_redis, mock_db, conversation_id
    ):
        """Invalidating only removes from Redis, not from DB."""
        await cache.invalidate(conversation_id)

        mock_redis.delete.assert_awaited_once()
        # DB should not be touched
        mock_db.execute.assert_not_awaited()
        mock_db.delete.assert_not_awaited()


class TestConversationCacheCreate:
    """Tests for ConversationCache.create."""

    async def test_create_conversation(self, cache, mock_redis, mock_db):
        """create() should create a conversation in DB and cache it in Redis."""
        user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

        # Mock the db add/commit/refresh cycle
        # After refresh, the conversation will have attributes set
        def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime(2024, 1, 1, tzinfo=UTC)
            obj.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
            obj.messages = []

        mock_db.refresh.side_effect = fake_refresh

        result = await cache.create(user_id=user_id, title="New Conversation")

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()
        mock_redis.setex.assert_awaited_once()
        assert result["title"] == "New Conversation"
        assert result["user_id"] == str(user_id)


class TestConversationCacheSyncToDb:
    """Tests for ConversationCache.sync_to_db."""

    async def test_sync_to_db_no_cached_data(self, cache, mock_redis, mock_db):
        """sync_to_db() should return False when no cached data exists."""
        mock_redis.get.return_value = None

        result = await cache.sync_to_db("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        assert result is False
        mock_redis.delete.assert_awaited_once()

    async def test_sync_to_db_new_conversation(self, cache, mock_redis, mock_db):
        """sync_to_db() should create a new conversation in DB when it does not exist."""
        conv_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        cached_data = {
            "id": conv_id,
            "user_id": "12345678-1234-5678-1234-567812345678",
            "session_id": None,
            "title": "Test",
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "role": "user",
                    "content": "Hello",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        # DB does not have the conversation
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await cache.sync_to_db(conv_id)

        assert result is True
        mock_db.add.assert_called()
        mock_db.commit.assert_awaited_once()
        mock_redis.delete.assert_awaited_once()

    async def test_sync_to_db_existing_conversation(self, cache, mock_redis, mock_db):
        """sync_to_db() should update an existing conversation in DB."""
        conv_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        cached_data = {
            "id": conv_id,
            "user_id": "12345678-1234-5678-1234-567812345678",
            "session_id": None,
            "title": "Updated Title",
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "role": "user",
                    "content": "Hello",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        # DB has the conversation already
        existing_conv = MagicMock()
        existing_conv.id = uuid.UUID(conv_id)
        existing_conv.messages = []
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_conv
        mock_db.execute.return_value = mock_result

        result = await cache.sync_to_db(conv_id)

        assert result is True
        assert existing_conv.title == "Updated Title"
        mock_db.commit.assert_awaited_once()
        mock_redis.delete.assert_awaited_once()

    async def test_sync_to_db_skips_existing_messages(self, cache, mock_redis, mock_db):
        """sync_to_db() should skip messages that already exist in the DB."""
        conv_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        existing_msg_id = str(uuid.uuid4())
        cached_data = {
            "id": conv_id,
            "user_id": "12345678-1234-5678-1234-567812345678",
            "session_id": None,
            "title": "Title",
            "messages": [
                {
                    "id": existing_msg_id,
                    "role": "user",
                    "content": "Already exists",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        # DB has the conversation with the same message already
        existing_msg = MagicMock()
        existing_msg.id = uuid.UUID(existing_msg_id)
        existing_conv = MagicMock()
        existing_conv.id = uuid.UUID(conv_id)
        existing_conv.messages = [existing_msg]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_conv
        mock_db.execute.return_value = mock_result

        result = await cache.sync_to_db(conv_id)

        assert result is True
        # No new messages should have been added (only commit + delete dirty flag)
        mock_db.add.assert_not_called()
        mock_db.commit.assert_awaited_once()


class TestConversationCacheGetRedis:
    """Tests for ConversationCache._get_redis."""

    @patch("backend.session.cache.redis.from_url")
    @patch("backend.session.cache.settings")
    async def test_get_redis_creates_connection(self, mock_settings, mock_from_url, mock_db):
        """_get_redis() creates a Redis connection when none exists."""
        mock_settings.session_redis_url = "redis://localhost:6379/3"
        mock_redis_instance = AsyncMock()
        mock_from_url.return_value = mock_redis_instance

        c = ConversationCache(db=mock_db)
        assert c._redis is None

        result = await c._get_redis()

        assert result is mock_redis_instance
        assert c._redis is mock_redis_instance
        mock_from_url.assert_called_once_with(
            "redis://localhost:6379/3",
            encoding="utf-8",
            decode_responses=True,
        )

    async def test_get_redis_reuses_existing_connection(self, mock_db):
        """_get_redis() returns existing connection without creating a new one."""
        existing_redis = AsyncMock()
        c = ConversationCache(db=mock_db)
        c._redis = existing_redis

        result = await c._get_redis()

        assert result is existing_redis


class TestConversationCacheClose:
    """Tests for ConversationCache.close."""

    async def test_close_closes_redis(self, cache, mock_redis):
        """Closing the cache closes the Redis connection."""
        await cache.close()

        mock_redis.close.assert_awaited_once()
        assert cache._redis is None

    async def test_close_when_redis_is_none(self, mock_db):
        """Closing the cache when no Redis connection was created does nothing."""
        c = ConversationCache(db=mock_db)
        c._redis = None

        await c.close()

        assert c._redis is None
