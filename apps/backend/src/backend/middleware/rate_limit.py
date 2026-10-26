# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Rate limiting with Redis backend."""

import time
from uuid import UUID

import redis.asyncio as redis

from backend.config import settings
from backend.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Rate limiter using Redis sliding window."""

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.rate_limit_redis_url,
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for rate limiting."""
        return f"ratelimit:{identifier}"

    async def check_rate_limit(
        self,
        user_id: UUID | str | None,
        client_ip: str,
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit.

        Args:
            user_id: Authenticated user ID or None for anonymous
            client_ip: Client IP address for anonymous users

        Returns:
            Tuple of (allowed, remaining, reset_seconds)
        """
        # Determine limit based on auth status
        if user_id:
            limit = settings.rate_limit_auth
            identifier = f"user:{user_id}"
        else:
            limit = settings.rate_limit_anon
            identifier = f"ip:{client_ip}"

        window = settings.rate_limit_window

        r = await self.get_redis()
        key = self._get_key(identifier)
        now = time.time()
        window_start = now - window

        pipe = r.pipeline()

        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current requests in window
        pipe.zcard(key)

        # Add current request
        pipe.zadd(key, {str(now): now})

        # Set expiry on the key
        pipe.expire(key, window)

        results = await pipe.execute()
        current_count = results[1]

        remaining = max(0, limit - current_count - 1)
        reset_seconds = int(window)

        if current_count >= limit:
            # Remove the request we just added since it's over limit
            await r.zrem(key, str(now))
            logger.info(
                "Rate limit exceeded (limit: %d/min)",
                limit,
                extra={"user_id": str(user_id) if user_id else None, "client_ip": client_ip},
            )
            return False, 0, reset_seconds

        logger.info(
            "Rate limit check: %d/%d requests",
            current_count + 1,
            limit,
            extra={"user_id": str(user_id) if user_id else None, "client_ip": client_ip},
        )
        return True, remaining, reset_seconds

    async def check_session_creation_limit(self, client_ip: str) -> tuple[bool, int, int]:
        """
        Check if a new session can be created for this IP.

        This is a separate rate limit specifically for session creation
        to prevent abuse (e.g., creating many sessions via curl).

        Args:
            client_ip: Client IP address

        Returns:
            Tuple of (allowed, remaining, reset_seconds)
        """
        limit = settings.session_create_limit
        window = settings.session_create_window
        identifier = f"session_create:{client_ip}"

        r = await self.get_redis()
        key = self._get_key(identifier)
        now = time.time()
        window_start = now - window

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        results = await pipe.execute()
        current_count = results[1]

        remaining = max(0, limit - current_count)
        reset_seconds = int(window)

        if current_count >= limit:
            logger.info(
                "Session creation limit exceeded (limit: %d/day)",
                limit,
                extra={"client_ip": client_ip},
            )
            return False, 0, reset_seconds

        return True, remaining, reset_seconds

    async def record_session_creation(self, client_ip: str) -> None:
        """Record a session creation for rate limiting purposes."""
        window = settings.session_create_window
        identifier = f"session_create:{client_ip}"

        r = await self.get_redis()
        key = self._get_key(identifier)
        now = time.time()

        pipe = r.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window)
        await pipe.execute()

        logger.info("Recorded session creation", extra={"client_ip": client_ip})


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


async def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
