# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery task for syncing dirty conversations from Redis to PostgreSQL."""

import asyncio

from backend.celery import celery_app
from backend.database import async_session_maker
from backend.logging import get_logger
from backend.session.cache import ConversationCache

logger = get_logger(__name__)


async def _sync_dirty_conversations() -> int:
    """Async implementation of conversation sync.

    Returns:
        Number of conversations synced
    """
    async with async_session_maker() as db:
        cache = ConversationCache(db)
        try:
            # Get all dirty conversation IDs
            dirty_ids = await cache.get_dirty_conversations()

            if not dirty_ids:
                logger.debug("No dirty conversations to sync")
                return 0

            logger.info("Syncing %d dirty conversations", len(dirty_ids))

            synced = 0
            for conv_id in dirty_ids:
                try:
                    success = await cache.sync_to_db(conv_id)
                    if success:
                        synced += 1
                except Exception as e:
                    logger.error("Failed to sync conversation %s: %s", conv_id[:8], str(e))

            logger.info("Synced %d/%d conversations", synced, len(dirty_ids))
            return synced

        finally:
            await cache.close()


@celery_app.task(name="sync_dirty_conversations")
def sync_dirty_conversations() -> int:
    """Celery task to sync dirty conversations from Redis to PostgreSQL.

    This task is scheduled to run periodically via Celery Beat.
    It finds all conversations marked as dirty in Redis and persists
    them to PostgreSQL.

    Returns:
        Number of conversations synced
    """
    return asyncio.run(_sync_dirty_conversations())
