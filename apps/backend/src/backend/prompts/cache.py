# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Redis cache for system prompts."""

import redis.asyncio as redis

from backend.config import settings
from backend.logging import get_logger

logger = get_logger(__name__)

# Redis key prefixes
SLUG_PREFIX = "prompt:slug:"
SCOPE_PREFIX = "prompt:scope:"
DEFAULT_KEY = "prompt:default"


class PromptCache:
    """Redis-based cache for system prompts.

    Caches prompt content by slug and by scope set for fast lookups.
    Uses Redis for shared cache across all workers.
    Supports TTL-based expiration and manual invalidation.
    """

    _instance: "PromptCache | None" = None
    _redis: redis.Redis | None = None
    _initialized: bool = False

    def __new__(cls) -> "PromptCache":
        """Singleton pattern for global cache instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize cache if not already initialized."""
        if self._initialized:
            return
        self._initialized = True

    @classmethod
    async def get_redis(cls) -> redis.Redis:
        """Get or create the Redis connection."""
        if cls._redis is None:
            cls._redis = redis.from_url(
                settings.prompt_cache_redis_url,
                decode_responses=True,
            )
            logger.info("Connected to Redis for prompt cache")
        return cls._redis

    @classmethod
    async def close(cls) -> None:
        """Close the Redis connection."""
        if cls._redis is not None:
            await cls._redis.close()
            cls._redis = None
            logger.info("Closed Redis connection for prompt cache")

    def _get_ttl(self) -> int | None:
        """Get TTL in seconds, or None if no expiration."""
        if settings.prompt_cache_ttl <= 0:
            return None
        return settings.prompt_cache_ttl

    def _scope_key(self, scopes: set[str] | None) -> str:
        """Generate Redis key for scopes."""
        if not scopes:
            return f"{SCOPE_PREFIX}__anonymous__"
        # Sort scopes for consistent key generation
        sorted_scopes = sorted(scopes)
        return f"{SCOPE_PREFIX}{':'.join(sorted_scopes)}"

    async def get_by_slug(self, slug: str) -> str | None:
        """Get cached prompt content by slug.

        Args:
            slug: Prompt slug

        Returns:
            Prompt content or None if not cached/expired
        """
        try:
            r = await self.get_redis()
            content = await r.get(f"{SLUG_PREFIX}{slug}")
            if content:
                logger.debug("Cache hit for slug: %s", slug)
                return content
            return None
        except redis.RedisError as e:
            logger.error("Redis error getting slug %s: %s", slug, e)
            return None

    async def set_by_slug(self, slug: str, content: str) -> None:
        """Cache prompt content by slug.

        Args:
            slug: Prompt slug
            content: Prompt content
        """
        try:
            r = await self.get_redis()
            ttl = self._get_ttl()
            if ttl:
                await r.setex(f"{SLUG_PREFIX}{slug}", ttl, content)
            else:
                await r.set(f"{SLUG_PREFIX}{slug}", content)
            logger.debug("Cached prompt for slug: %s", slug)
        except redis.RedisError as e:
            logger.error("Redis error setting slug %s: %s", slug, e)

    async def get_for_scopes(self, scopes: set[str] | None) -> str | None:
        """Get cached prompt content for user scopes.

        Args:
            scopes: User's scopes (None for anonymous)

        Returns:
            Prompt content or None if not cached/expired
        """
        try:
            r = await self.get_redis()
            key = self._scope_key(scopes)
            content = await r.get(key)
            if content:
                logger.debug("Cache hit for scopes: %s", scopes)
                return content
            return None
        except redis.RedisError as e:
            logger.error("Redis error getting scopes %s: %s", scopes, e)
            return None

    async def set_for_scopes(self, scopes: set[str] | None, content: str) -> None:
        """Cache prompt content for user scopes.

        Args:
            scopes: User's scopes (None for anonymous)
            content: Prompt content
        """
        try:
            r = await self.get_redis()
            key = self._scope_key(scopes)
            ttl = self._get_ttl()
            if ttl:
                await r.setex(key, ttl, content)
            else:
                await r.set(key, content)
            logger.debug("Cached prompt for scopes: %s", scopes)
        except redis.RedisError as e:
            logger.error("Redis error setting scopes %s: %s", scopes, e)

    async def get_default(self) -> str | None:
        """Get cached default prompt content.

        Returns:
            Default prompt content or None if not cached/expired
        """
        try:
            r = await self.get_redis()
            content = await r.get(DEFAULT_KEY)
            if content:
                logger.debug("Cache hit for default prompt")
                return content
            return None
        except redis.RedisError as e:
            logger.error("Redis error getting default prompt: %s", e)
            return None

    async def set_default(self, content: str) -> None:
        """Cache default prompt content.

        Args:
            content: Default prompt content
        """
        try:
            r = await self.get_redis()
            ttl = self._get_ttl()
            if ttl:
                await r.setex(DEFAULT_KEY, ttl, content)
            else:
                await r.set(DEFAULT_KEY, content)
            logger.debug("Cached default prompt")
        except redis.RedisError as e:
            logger.error("Redis error setting default prompt: %s", e)

    async def invalidate(self, slug: str | None = None) -> None:
        """Invalidate cache entries.

        Args:
            slug: If provided, invalidate only this slug.
                  If None, invalidate all entries.
        """
        try:
            r = await self.get_redis()
            if slug:
                # Delete specific slug
                await r.delete(f"{SLUG_PREFIX}{slug}")
                logger.info("Invalidated cache for slug: %s", slug)
                # Also clear all scope caches as the slug might affect scope resolution
                async for key in r.scan_iter(f"{SCOPE_PREFIX}*"):
                    await r.delete(key)
                logger.debug("Cleared scope cache after slug invalidation")
            else:
                # Delete all prompt cache keys
                async for key in r.scan_iter(f"{SLUG_PREFIX}*"):
                    await r.delete(key)
                async for key in r.scan_iter(f"{SCOPE_PREFIX}*"):
                    await r.delete(key)
                await r.delete(DEFAULT_KEY)
                logger.info("Invalidated all prompt caches")
        except redis.RedisError as e:
            logger.error("Redis error invalidating cache: %s", e)

    async def clear(self) -> None:
        """Clear all cache entries."""
        await self.invalidate()


# Global cache instance
prompt_cache = PromptCache()
