# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OIDC UserInfo client with Redis caching.

Fetches user profile (email, name, etc.) from the auth server's
/userinfo endpoint using the access token.
"""

import hashlib
import json
from typing import Any

import httpx
import redis.asyncio as redis

from apt_server.auth.jwks import jwks_manager
from apt_server.config import settings
from apt_server.logging import get_logger

logger = get_logger(__name__)


class UserInfoClient:
    """Client for OIDC UserInfo endpoint.

    Fetches user claims (email, name, picture, etc.) from the auth server.
    Caches results in Redis keyed by token hash.
    """

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: redis.Redis | None = None

    @property
    def is_configured(self) -> bool:
        """Check if userinfo is available."""
        return jwks_manager.is_configured

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def _get_redis_client(self) -> redis.Redis | None:
        """Get or create Redis client if configured."""
        if not settings.redis_url:
            return None

        if self._redis_client is None:
            self._redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis_client

    def _cache_key(self, token: str) -> str:
        """Generate cache key for userinfo."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        return f"{settings.redis_key_prefix}:userinfo:{token_hash}"

    async def _get_cached(self, token: str) -> dict[str, Any] | None:
        """Get cached userinfo result."""
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return None

        try:
            cached = await redis_client.get(self._cache_key(token))
            if cached:
                data: dict[str, Any] = json.loads(cached)
                return data
        except Exception as e:
            logger.warning("Redis cache read error: %s", e)

        return None

    async def _set_cached(self, token: str, result: dict[str, Any]) -> None:
        """Cache userinfo result."""
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return

        try:
            await redis_client.setex(
                self._cache_key(token),
                settings.userinfo_cache_ttl,
                json.dumps(result),
            )
        except Exception as e:
            logger.warning("Redis cache write error: %s", e)

    async def get_userinfo(self, token: str) -> dict[str, Any]:
        """Fetch user profile from the OIDC UserInfo endpoint.

        Args:
            token: The user's access token (must have openid scope).

        Returns:
            UserInfo claims dict (sub, email, name, picture, etc.)

        Raises:
            httpx.HTTPStatusError: If the request fails.
            ValueError: If OAuth2 is not configured.
        """
        if not self.is_configured:
            raise ValueError("OAuth2 issuer not configured")

        # Check cache first
        cached = await self._get_cached(token)
        if cached:
            logger.debug("UserInfo cache hit")
            return cached

        # Discover userinfo endpoint from OIDC config
        config = await jwks_manager.fetch_issuer_config()
        userinfo_endpoint = config.get("userinfo_endpoint")
        if not userinfo_endpoint:
            raise ValueError("userinfo_endpoint not found in issuer config")

        client = await self._get_http_client()
        response = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        result: dict[str, Any] = response.json()
        await self._set_cached(token, result)

        logger.debug("UserInfo fetched for sub=%s", result.get("sub"))
        return result

    async def close(self) -> None:
        """Close HTTP and Redis clients."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None


# Global userinfo client instance
userinfo_client = UserInfoClient()
