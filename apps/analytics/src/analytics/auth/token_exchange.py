# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Token Exchange client (RFC 8693) with Redis caching."""

import hashlib
import json
from typing import Any

import httpx
import redis.asyncio as redis

from analytics.config import settings
from analytics.logging import get_logger

logger = get_logger(__name__)


class TokenExchangeError(Exception):
    """Token exchange failed."""

    def __init__(self, message: str, error_code: str = "exchange_error"):
        super().__init__(message)
        self.error_code = error_code


class TokenExchangeClient:
    """Client for OAuth2 Token Exchange (RFC 8693).

    Uses token exchange to validate user tokens and check if they have
    the required scopes. Caches exchange results in Redis.
    """

    GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
    TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: redis.Redis | None = None

    @property
    def is_configured(self) -> bool:
        """Check if token exchange is configured."""
        return (
            bool(settings.oauth2_client_id)
            and bool(settings.oauth2_client_secret)
            and bool(settings.oauth2_issuer)
        )

    @property
    def issuer(self) -> str:
        """Get the OAuth2 issuer URL."""
        return settings.oauth2_issuer.rstrip("/")

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

    def _cache_key(self, token: str, scopes: list[str]) -> str:
        """Generate cache key for token + scopes combination."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        scopes_hash = hashlib.sha256(",".join(sorted(scopes)).encode()).hexdigest()[:8]
        return f"analytics:tex:{token_hash}:{scopes_hash}"

    async def _get_cached(self, token: str, scopes: list[str]) -> dict[str, Any] | None:
        """Get cached token exchange result."""
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return None

        try:
            cached = await redis_client.get(self._cache_key(token, scopes))
            if cached:
                result: dict[str, Any] = json.loads(cached)
                return result
        except Exception as e:
            logger.warning("Redis cache read error: %s", e)

        return None

    async def _set_cached(self, token: str, scopes: list[str], result: dict[str, Any]) -> None:
        """Cache token exchange result."""
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return

        try:
            await redis_client.setex(
                self._cache_key(token, scopes),
                settings.oauth2_client_cache_ttl,
                json.dumps(result),
            )
        except Exception as e:
            logger.warning("Redis cache write error: %s", e)

    async def exchange_token(
        self,
        subject_token: str,
        requested_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Exchange a user token for an API token with specific scopes.

        This validates that the user has the required scopes by attempting
        a token exchange with the auth server. The auth server will only
        issue a new token if the user has been granted the requested scopes.

        Args:
            subject_token: The user's access token
            requested_scopes: Scopes to request (if None, uses original scopes)

        Returns:
            Dictionary with exchanged token info:
            - access_token: The new access token
            - token_type: Bearer
            - expires_in: Token lifetime in seconds
            - scope: Granted scopes (space-separated)

        Raises:
            TokenExchangeError: If exchange fails (invalid token, insufficient scopes)
        """
        if not self.is_configured:
            raise TokenExchangeError("Token exchange not configured")

        scopes = requested_scopes or []

        # Check cache first
        cached = await self._get_cached(subject_token, scopes)
        if cached:
            logger.debug("Token exchange cache hit")
            return cached

        # Perform token exchange
        client = await self._get_http_client()

        data = {
            "grant_type": self.GRANT_TYPE,
            "subject_token": subject_token,
            "subject_token_type": self.TOKEN_TYPE_ACCESS,
            "client_id": settings.oauth2_client_id,
            "client_secret": settings.oauth2_client_secret,
        }

        if scopes:
            data["scope"] = " ".join(scopes)

        response = await client.post(
            f"{self.issuer}/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            error_data = {}
            try:
                if response.content:
                    error_data = response.json()
            except Exception:
                pass

            error = error_data.get("error", "unknown_error")
            error_description = error_data.get("error_description", "Token exchange failed")

            logger.error(
                "Token exchange failed: status=%s, error=%s, description=%s",
                response.status_code,
                error,
                error_description,
            )

            raise TokenExchangeError(
                f"{error}: {error_description}",
                error_code=error,
            )

        result: dict[str, Any] = response.json()

        # Cache successful result
        await self._set_cached(subject_token, scopes, result)

        return result

    async def validate_token_scopes(
        self,
        token: str,
        required_scopes: list[str],
    ) -> dict[str, Any]:
        """Validate that a token has the required scopes.

        Attempts token exchange with the required scopes. If successful,
        the user has been granted those scopes via RBAC.

        Args:
            token: User's access token
            required_scopes: Scopes required for the operation

        Returns:
            Token exchange result including granted scopes

        Raises:
            TokenExchangeError: If validation fails
        """
        return await self.exchange_token(token, required_scopes)

    async def close(self) -> None:
        """Close HTTP and Redis clients."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None


# Global token exchange client instance
token_exchange_client = TokenExchangeClient()
