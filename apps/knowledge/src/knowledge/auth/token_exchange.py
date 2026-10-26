# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Token exchange service for scope limitation (RFC 8693)."""

import hashlib
import json
import logging
from typing import Any

import httpx
import redis.asyncio as redis

from knowledge.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TokenExchangeError(Exception):
    """Token exchange failed."""

    pass


class TokenExchangeClient:
    """Client for OAuth2 token exchange (RFC 8693).

    Used to exchange user tokens for API-specific tokens with limited scopes.
    This ensures the API only receives the scopes it needs, not all user scopes.
    """

    GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
    TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"

    def __init__(self) -> None:
        self.issuer = settings.oauth2_issuer
        self.client_id = settings.oauth2_client_id
        self.client_secret = settings.oauth2_client_secret
        self.cache_ttl = settings.oauth2_token_cache_ttl
        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: redis.Redis | None = None

    async def get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def get_redis_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis_client

    def _cache_key(self, token: str, scopes: list[str]) -> str:
        """Generate cache key for token exchange result."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        scopes_hash = hashlib.sha256(",".join(sorted(scopes)).encode()).hexdigest()[:8]
        return f"knowledge:token_exchange:{token_hash}:{scopes_hash}"

    async def exchange_token(
        self,
        subject_token: str,
        requested_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Exchange a user token for an API token with specific scopes.

        Args:
            subject_token: The user's access token.
            requested_scopes: Scopes to request for the new token.

        Returns:
            Token response with access_token, token_type, expires_in, scope.

        Raises:
            TokenExchangeError: If exchange fails.
        """
        if not self.issuer or not self.client_id or not self.client_secret:
            raise TokenExchangeError("OAuth2 client not configured for token exchange")

        scopes = requested_scopes or []

        # Check cache first
        cache_key = self._cache_key(subject_token, scopes)
        try:
            redis_client = await self.get_redis_client()
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug(f"Token exchange cache hit: {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")

        # Perform token exchange
        try:
            client = await self.get_http_client()
            response = await client.post(
                f"{self.issuer}/oauth2/token",
                data={
                    "grant_type": self.GRANT_TYPE,
                    "subject_token": subject_token,
                    "subject_token_type": self.TOKEN_TYPE,
                    "scope": " ".join(scopes) if scopes else None,
                },
                auth=(self.client_id, self.client_secret),
            )

            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error_description", response.text)
                raise TokenExchangeError(f"Token exchange failed: {error_msg}")

            result = response.json()

            # Cache the result
            try:
                await redis_client.setex(
                    cache_key,
                    self.cache_ttl,
                    json.dumps(result),
                )
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")

            return result

        except httpx.RequestError as e:
            raise TokenExchangeError(f"Token exchange request failed: {e}")

    async def validate_token_scopes(
        self,
        subject_token: str,
        required_scopes: list[str],
    ) -> dict[str, Any]:
        """Validate that a token can be exchanged for required scopes.

        This is used to check if a user has permission for specific operations
        without actually using the exchanged token.

        Args:
            subject_token: The user's access token.
            required_scopes: Scopes required for the operation.

        Returns:
            Token exchange result with granted scopes.

        Raises:
            TokenExchangeError: If exchange fails or scopes not granted.
        """
        result = await self.exchange_token(subject_token, required_scopes)

        granted_scopes = set(result.get("scope", "").split())
        required_set = set(required_scopes)

        # Check if all required scopes were granted
        missing = required_set - granted_scopes
        if missing:
            raise TokenExchangeError(f"Required scopes not granted: {', '.join(missing)}")

        return result

    async def close(self) -> None:
        """Close HTTP and Redis clients."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        if self._redis_client:
            await self._redis_client.aclose()


# Singleton instance
_token_exchange_client: TokenExchangeClient | None = None


def get_token_exchange_client() -> TokenExchangeClient:
    """Get or create the token exchange client singleton."""
    global _token_exchange_client
    if _token_exchange_client is None:
        _token_exchange_client = TokenExchangeClient()
    return _token_exchange_client
