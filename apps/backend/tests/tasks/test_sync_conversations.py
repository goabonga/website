# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.tasks.sync_conversations."""

from unittest.mock import AsyncMock, MagicMock, patch


class TestSyncDirtyConversations:
    """Tests for _sync_dirty_conversations async function."""

    @patch("backend.tasks.sync_conversations.ConversationCache")
    @patch("backend.tasks.sync_conversations.async_session_maker")
    async def test_no_dirty_conversations_returns_zero(self, mock_session_maker, mock_cache_cls):
        """Returns 0 when there are no dirty conversations."""
        from backend.tasks.sync_conversations import _sync_dirty_conversations

        # Setup mock session context manager
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        # Setup mock cache
        mock_cache = AsyncMock()
        mock_cache.get_dirty_conversations = AsyncMock(return_value=[])
        mock_cache.close = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        result = await _sync_dirty_conversations()

        assert result == 0
        mock_cache.close.assert_awaited_once()

    @patch("backend.tasks.sync_conversations.ConversationCache")
    @patch("backend.tasks.sync_conversations.async_session_maker")
    async def test_syncs_dirty_conversations(self, mock_session_maker, mock_cache_cls):
        """Syncs dirty conversations and returns the count."""
        from backend.tasks.sync_conversations import _sync_dirty_conversations

        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_cache = AsyncMock()
        mock_cache.get_dirty_conversations = AsyncMock(return_value=["conv-1111", "conv-2222"])
        mock_cache.sync_to_db = AsyncMock(return_value=True)
        mock_cache.close = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        result = await _sync_dirty_conversations()

        assert result == 2
        assert mock_cache.sync_to_db.await_count == 2

    @patch("backend.tasks.sync_conversations.ConversationCache")
    @patch("backend.tasks.sync_conversations.async_session_maker")
    async def test_sync_failure_continues_with_others(self, mock_session_maker, mock_cache_cls):
        """If one conversation fails to sync, others continue."""
        from backend.tasks.sync_conversations import _sync_dirty_conversations

        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_cache = AsyncMock()
        mock_cache.get_dirty_conversations = AsyncMock(
            return_value=["conv-aaaa", "conv-bbbb", "conv-cccc"]
        )
        # First call fails, second and third succeed
        mock_cache.sync_to_db = AsyncMock(side_effect=[Exception("Redis error"), True, True])
        mock_cache.close = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        result = await _sync_dirty_conversations()

        assert result == 2
        assert mock_cache.sync_to_db.await_count == 3

    @patch("backend.tasks.sync_conversations.ConversationCache")
    @patch("backend.tasks.sync_conversations.async_session_maker")
    async def test_sync_to_db_returns_false_does_not_count(
        self, mock_session_maker, mock_cache_cls
    ):
        """When sync_to_db returns False, it is not counted in the synced total."""
        from backend.tasks.sync_conversations import _sync_dirty_conversations

        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_cache = AsyncMock()
        mock_cache.get_dirty_conversations = AsyncMock(
            return_value=["conv-aaaa", "conv-bbbb", "conv-cccc"]
        )
        # First returns False, second and third return True
        mock_cache.sync_to_db = AsyncMock(side_effect=[False, True, True])
        mock_cache.close = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        result = await _sync_dirty_conversations()

        assert result == 2
        assert mock_cache.sync_to_db.await_count == 3

    @patch("backend.tasks.sync_conversations._sync_dirty_conversations", new_callable=MagicMock)
    @patch("backend.tasks.sync_conversations.asyncio")
    @patch("backend.tasks.sync_conversations.celery_app")
    def test_celery_task_calls_asyncio_run(self, mock_celery_app, mock_asyncio, mock_sync_fn):
        """The sync_dirty_conversations Celery task calls asyncio.run."""
        from backend.tasks.sync_conversations import sync_dirty_conversations

        mock_asyncio.run = MagicMock(return_value=5)

        result = sync_dirty_conversations()

        assert result == 5
        mock_asyncio.run.assert_called_once()
