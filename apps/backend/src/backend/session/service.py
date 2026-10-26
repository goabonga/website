# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Session service for managing anonymous user sessions."""

import json
import uuid

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.logging import get_logger
from backend.models.session import AnonymousSession

logger = get_logger(__name__)


class SessionService:
    """Service for managing anonymous user sessions with Redis caching."""

    REDIS_KEY_PREFIX = "anon:session:"

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

    def _redis_key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"{self.REDIS_KEY_PREFIX}{session_id}"

    async def get(self, session_id: str) -> dict | None:
        """Get session data from cache or database.

        Args:
            session_id: The session ID (UUID string from client)

        Returns:
            Session data dict or None if not found
        """
        r = await self._get_redis()
        key = self._redis_key(session_id)

        # Try Redis first
        cached = await r.get(key)
        if cached:
            logger.info("Session cache hit", extra={"session_id": session_id[:8]})
            data = json.loads(cached)
            # Refresh TTL on access
            await r.expire(key, settings.session_redis_ttl)
            return data

        # Cache miss - try database
        logger.info("Session cache miss", extra={"session_id": session_id[:8]})
        stmt = select(AnonymousSession).where(AnonymousSession.session_id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if session:
            # Cache the session
            data = {
                "id": str(session.id),
                "session_id": session.session_id,
                "created_at": session.created_at.isoformat(),
                "last_active": session.last_active.isoformat(),
            }
            await r.setex(key, settings.session_redis_ttl, json.dumps(data))
            logger.info("Session loaded from DB and cached", extra={"session_id": session_id[:8]})
            return data

        return None

    async def create(self, session_id: str) -> dict:
        """Create a new anonymous session.

        Args:
            session_id: The session ID (UUID string from client)

        Returns:
            Session data dict
        """
        # Validate UUID format
        try:
            uuid.UUID(session_id)
        except ValueError:
            logger.warning(
                "Invalid session ID format: %s", session_id[:8] if session_id else "empty"
            )
            raise ValueError("Invalid session ID format")

        # Create in database
        session = AnonymousSession(session_id=session_id)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        # Cache the session
        data = {
            "id": str(session.id),
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat(),
        }

        r = await self._get_redis()
        key = self._redis_key(session_id)
        await r.setex(key, settings.session_redis_ttl, json.dumps(data))

        logger.info("Created new anonymous session", extra={"session_id": session_id[:8]})
        return data

    async def get_or_create(self, session_id: str) -> dict:
        """Get existing session or create a new one.

        Args:
            session_id: The session ID (UUID string from client)

        Returns:
            Session data dict
        """
        session = await self.get(session_id)
        if session:
            return session
        return await self.create(session_id)

    async def delete(self, session_id: str) -> bool:
        """Delete an anonymous session from cache and database.

        Args:
            session_id: The session ID to delete

        Returns:
            True if session was deleted, False if not found
        """
        r = await self._get_redis()
        key = self._redis_key(session_id)

        # Delete from database
        stmt = select(AnonymousSession).where(AnonymousSession.session_id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if session:
            await self.db.delete(session)
            await self.db.commit()

        # Delete from cache
        await r.delete(key)

        if session:
            logger.info("Deleted anonymous session", extra={"session_id": session_id[:8]})
            return True

        logger.info("Session not found for deletion", extra={"session_id": session_id[:8]})
        return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
