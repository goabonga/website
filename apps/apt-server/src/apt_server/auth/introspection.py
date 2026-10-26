# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Token introspection client (RFC 7662) with Redis caching."""

import hashlib
from typing import Any

import httpx
import jwt
import redis.asyncio as redis

from apt_server.auth.jwks import jwks_manager
from apt_server.config import settings
from apt_server.logging import get_logger

logger = get_logger(__name__)


class TokenRevokedError(Exception):
    """Raised when a token has been revoked."""


class IntrospectionClient:
    """Client for OAuth2 Token Introspection (RFC 7662).

    Validates tokens against the auth server's introspection endpoint
    to detect revoked tokens. Caches results in Redis.
    """

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: redis.Redis | None = None

    @property
    def is_configured(self) -> bool:
        """Check if introspection is configured."""
        return (
            bool(settings.oauth2_client_id)
            and bool(settings.oauth2_client_secret)
            and jwks_manager.is_configured
        )

    @property
    def introspection_uri(self) -> str:
        """Get the token introspection endpoint URI."""
        return f"{jwks_manager.issuer}/oauth2/introspect"

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
        """Generate cache key for token introspection."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        return f"{settings.redis_key_prefix}:introspect:{token_hash}"

    async def _get_cached(self, token: str) -> bool | None:
        """Get cached introspection result."""
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return None

        try:
            cached = await redis_client.get(self._cache_key(token))
            if cached is not None:
                return bool(cached == "1")
        except Exception as e:
            logger.warning("Redis cache read error: %s", e)

        return None

    async def _set_cached(self, token: str, is_active: bool) -> None:
        """Cache introspection result."""
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return

        try:
            await redis_client.setex(
                self._cache_key(token),
                settings.token_introspection_cache_ttl,
                "1" if is_active else "0",
            )
        except Exception as e:
            logger.warning("Redis cache write error: %s", e)

    async def _introspect_request(
        self, token: str, token_type_hint: str | None = "access_token"
    ) -> dict[str, Any]:
        """Perform raw introspection request and return full response."""
        data: dict[str, str] = {
            "token": token,
            "client_id": settings.oauth2_client_id,
            "client_secret": settings.oauth2_client_secret,
        }
        if token_type_hint is not None:
            data["token_type_hint"] = token_type_hint

        client = await self._get_http_client()
        response = await client.post(
            self.introspection_uri,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def introspect_token(self, token: str) -> bool:
        """Check if a token is active via OAuth2 token introspection (RFC 7662).

        Args:
            token: The access token to introspect

        Returns:
            True if token is active, False if revoked/expired/invalid
        """
        if not self.is_configured:
            logger.warning("Introspection not configured, skipping")
            return True

        cached = await self._get_cached(token)
        if cached is not None:
            logger.debug("Token introspection cache hit: active=%s", cached)
            return cached

        try:
            result = await self._introspect_request(token)

            is_active = bool(result.get("active", False))
            await self._set_cached(token, is_active)

            logger.debug("Token introspection result: active=%s", is_active)
            return is_active

        except Exception as e:
            logger.warning("Token introspection failed: %s", e)
            return True

    async def validate_opaque_token(self, token: str) -> dict[str, Any]:
        """Validate an opaque token (e.g. PersonalAccessToken) via introspection only.

        Args:
            token: The opaque token to validate

        Returns:
            Introspection response claims

        Raises:
            jwt.InvalidTokenError: If introspection request fails
            TokenRevokedError: If token is not active
        """
        try:
            result = await self._introspect_request(token, token_type_hint=None)
        except Exception as e:
            logger.error("Opaque token introspection request failed: %s", e)
            raise jwt.InvalidTokenError(f"Token introspection failed: {e}")

        if not result.get("active", False):
            logger.warning("Opaque token introspection returned inactive")
            raise TokenRevokedError("Token is not active")

        await self._set_cached(token, True)

        logger.debug("Opaque token validated via introspection")
        return result

    async def validate_token_with_introspection(self, token: str) -> dict[str, Any]:
        """Validate JWT token with introspection check.

        Validates the token signature via JWKS, then checks if the token
        has been revoked via introspection.

        Args:
            token: The JWT token to validate

        Returns:
            Decoded JWT claims

        Raises:
            jwt.InvalidTokenError: If token signature is invalid
            TokenRevokedError: If token has been revoked
        """
        claims = await jwks_manager.validate_token(token)

        is_active = await self.introspect_token(token)
        if not is_active:
            raise TokenRevokedError("Token has been revoked")

        return claims

    async def close(self) -> None:
        """Close HTTP and Redis clients."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None


# Global introspection client instance
introspection_client = IntrospectionClient()
