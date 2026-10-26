# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Conversation cache with Redis for fast read/write operations."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.logging import get_logger
from backend.models.conversation import Conversation, Message

logger = get_logger(__name__)


class ConversationCache:
    """Redis-backed cache for conversations with read-through and dirty tracking."""

    CONV_KEY_PREFIX = "conv:"
    DIRTY_KEY_PREFIX = "conv:dirty:"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.session_redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _conv_key(self, conversation_id: str) -> str:
        """Generate Redis key for conversation."""
        return f"{self.CONV_KEY_PREFIX}{conversation_id}"

    def _dirty_key(self, conversation_id: str) -> str:
        """Generate Redis key for dirty flag."""
        return f"{self.DIRTY_KEY_PREFIX}{conversation_id}"

    def _serialize_conversation(self, conv: Conversation) -> dict[str, Any]:
        """Serialize conversation to dict for Redis storage."""
        return {
            "id": str(conv.id),
            "user_id": str(conv.user_id) if conv.user_id else None,
            "session_id": conv.session_id,
            "title": conv.title,
            "messages": [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in conv.messages
            ],
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
        }

    async def get(self, conversation_id: uuid.UUID) -> dict[str, Any] | None:
        """Get conversation from cache or database.

        Args:
            conversation_id: The conversation UUID

        Returns:
            Conversation data dict or None if not found
        """
        r = await self._get_redis()
        key = self._conv_key(str(conversation_id))

        # Try Redis first
        cached = await r.get(key)
        if cached:
            logger.debug("Conversation cache hit: %s", str(conversation_id)[:8])
            data = json.loads(cached)
            # Refresh TTL on access
            await r.expire(key, settings.conversation_cache_ttl)
            return data

        # Cache miss - load from database
        logger.debug("Conversation cache miss: %s", str(conversation_id)[:8])
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        result = await self.db.execute(stmt)
        conv = result.scalar_one_or_none()

        if conv:
            data = self._serialize_conversation(conv)
            await r.setex(key, settings.conversation_cache_ttl, json.dumps(data))
            logger.debug("Conversation loaded from DB and cached: %s", str(conversation_id)[:8])
            return data

        return None

    async def create(
        self,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Create a new conversation.

        Args:
            user_id: Optional user ID (for authenticated users)
            session_id: Optional session ID (for anonymous users)
            title: Optional conversation title

        Returns:
            Conversation data dict
        """
        conv = Conversation(
            user_id=user_id,
            session_id=session_id,
            title=title,
        )
        self.db.add(conv)
        await self.db.commit()
        await self.db.refresh(conv)

        data = self._serialize_conversation(conv)

        # Cache the new conversation
        r = await self._get_redis()
        key = self._conv_key(str(conv.id))
        await r.setex(key, settings.conversation_cache_ttl, json.dumps(data))

        logger.info(
            "Created new conversation: %s (user=%s, session=%s)",
            str(conv.id)[:8],
            str(user_id)[:8] if user_id else "none",
            session_id[:8] if session_id else "none",
        )
        return data

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        """Add a message to a conversation (write to cache, mark dirty).

        Args:
            conversation_id: The conversation UUID
            role: Message role (user, assistant, system)
            content: Message content

        Returns:
            The new message data dict
        """
        r = await self._get_redis()
        key = self._conv_key(str(conversation_id))
        dirty_key = self._dirty_key(str(conversation_id))

        # Get current conversation from cache
        conv_data = await self.get(conversation_id)
        if not conv_data:
            raise ValueError(f"Conversation not found: {conversation_id}")

        # Create new message data
        now = datetime.now(UTC)
        message_data = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "created_at": now.isoformat(),
        }

        # Update conversation in cache
        conv_data["messages"].append(message_data)
        conv_data["updated_at"] = now.isoformat()

        # Write back to cache
        await r.setex(key, settings.conversation_cache_ttl, json.dumps(conv_data))

        # Mark as dirty for sync
        await r.set(dirty_key, "1")

        logger.debug(
            "Added message to conversation %s (role=%s, dirty=true)", str(conversation_id)[:8], role
        )
        return message_data

    async def update_title(self, conversation_id: uuid.UUID, title: str) -> dict[str, Any] | None:
        """Update conversation title.

        Args:
            conversation_id: The conversation UUID
            title: New title

        Returns:
            Updated conversation data or None if not found
        """
        r = await self._get_redis()
        key = self._conv_key(str(conversation_id))
        dirty_key = self._dirty_key(str(conversation_id))

        conv_data = await self.get(conversation_id)
        if not conv_data:
            return None

        conv_data["title"] = title
        conv_data["updated_at"] = datetime.now(UTC).isoformat()

        await r.setex(key, settings.conversation_cache_ttl, json.dumps(conv_data))
        await r.set(dirty_key, "1")

        logger.debug("Updated conversation title: %s", str(conversation_id)[:8])
        return conv_data

    async def get_dirty_conversations(self) -> list[str]:
        """Get list of conversation IDs marked as dirty.

        Returns:
            List of conversation ID strings
        """
        r = await self._get_redis()
        keys = []
        async for key in r.scan_iter(f"{self.DIRTY_KEY_PREFIX}*"):
            conv_id = key.replace(self.DIRTY_KEY_PREFIX, "")
            keys.append(conv_id)
        return keys

    async def sync_to_db(self, conversation_id: str) -> bool:
        """Sync a cached conversation to the database.

        Args:
            conversation_id: The conversation ID string

        Returns:
            True if synced successfully, False otherwise
        """
        r = await self._get_redis()
        key = self._conv_key(conversation_id)
        dirty_key = self._dirty_key(conversation_id)

        # Get cached data
        cached = await r.get(key)
        if not cached:
            logger.warning("No cached data for conversation: %s", conversation_id[:8])
            await r.delete(dirty_key)
            return False

        data = json.loads(cached)
        conv_uuid = uuid.UUID(conversation_id)

        # Get or create conversation in DB
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conv_uuid)
        )
        result = await self.db.execute(stmt)
        conv = result.scalar_one_or_none()

        if not conv:
            # Create new conversation
            conv = Conversation(
                id=conv_uuid,
                user_id=uuid.UUID(data["user_id"]) if data.get("user_id") else None,
                session_id=data.get("session_id"),
                title=data.get("title"),
            )
            self.db.add(conv)
        else:
            # Update existing
            conv.title = data.get("title")
            conv.session_id = data.get("session_id")

        # Sync messages - get existing message IDs
        existing_msg_ids = {str(msg.id) for msg in conv.messages}

        # Add new messages
        for msg_data in data.get("messages", []):
            if msg_data["id"] not in existing_msg_ids:
                msg = Message(
                    id=uuid.UUID(msg_data["id"]),
                    conversation_id=conv_uuid,
                    role=msg_data["role"],
                    content=msg_data["content"],
                )
                self.db.add(msg)

        await self.db.commit()

        # Clear dirty flag
        await r.delete(dirty_key)

        logger.info(
            "Synced conversation to DB: %s (%d messages)",
            conversation_id[:8],
            len(data.get("messages", [])),
        )
        return True

    async def delete(self, conversation_id: uuid.UUID) -> bool:
        """Delete a conversation from cache and database.

        Args:
            conversation_id: The conversation UUID

        Returns:
            True if deleted, False if not found
        """
        r = await self._get_redis()
        key = self._conv_key(str(conversation_id))
        dirty_key = self._dirty_key(str(conversation_id))

        # Delete from database
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conv = result.scalar_one_or_none()

        if conv:
            await self.db.delete(conv)
            await self.db.commit()

        # Delete from cache
        await r.delete(key, dirty_key)

        logger.info("Deleted conversation: %s", str(conversation_id)[:8])
        return conv is not None

    async def invalidate(self, conversation_id: uuid.UUID) -> None:
        """Invalidate a conversation in cache (remove from Redis only).

        Use this when the database state has changed and the cache
        needs to be refreshed on next access.

        Args:
            conversation_id: The conversation UUID
        """
        r = await self._get_redis()
        key = self._conv_key(str(conversation_id))
        dirty_key = self._dirty_key(str(conversation_id))

        await r.delete(key, dirty_key)
        logger.debug("Invalidated conversation cache: %s", str(conversation_id)[:8])

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
