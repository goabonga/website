# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWT validation with JWKS support and token introspection."""

import hashlib
from typing import Any

import httpx
import redis.asyncio as redis
from jose import JWTError, jwt

from internal.config import settings
from internal.logging import get_logger

logger = get_logger(__name__)


class TokenRevokedError(Exception):
    """Raised when a token has been revoked."""

    pass


class JWTValidator:
    """JWT validator with JWKS caching and token introspection."""

    def __init__(self):
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at: float = 0
        self._jwks_cache_ttl: int = 3600  # 1 hour
        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: redis.Redis | None = None

    @property
    def issuer(self) -> str:
        """Get the OIDC issuer URL."""
        return settings.oauth2_issuer.rstrip("/")

    @property
    def jwks_uri(self) -> str:
        """Get the JWKS URI from the issuer."""
        return f"{self.issuer}/.well-known/jwks.json"

    @property
    def introspection_uri(self) -> str:
        """Get the token introspection endpoint URI."""
        return f"{self.issuer}/oauth2/introspect"

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

    async def _fetch_jwks(self) -> dict[str, Any]:
        """Fetch JWKS from the issuer."""
        client = await self._get_http_client()
        response = await client.get(self.jwks_uri)
        response.raise_for_status()
        return response.json()

    async def get_jwks(self) -> dict[str, Any]:
        """Get JWKS with caching."""
        import time

        now = time.time()
        if self._jwks is None or now >= self._jwks_expires_at:
            try:
                self._jwks = await self._fetch_jwks()
                self._jwks_expires_at = now + self._jwks_cache_ttl
                logger.debug("Refreshed JWKS from %s", self.jwks_uri)
            except Exception as e:
                if self._jwks is not None:
                    logger.warning("Failed to refresh JWKS, using cache: %s", e)
                else:
                    raise
        return self._jwks

    async def validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return claims."""
        jwks = await self.get_jwks()

        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            key = None
            for jwk in jwks.get("keys", []):
                if jwk.get("kid") == kid:
                    key = jwk
                    break

            if key is None:
                raise JWTError("No matching key found in JWKS")

            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                issuer=self.issuer,
                options={"verify_aud": False},
            )

            return claims

        except JWTError:
            raise
        except Exception as e:
            raise JWTError(f"Token validation failed: {e}")

    def _cache_key(self, token: str) -> str:
        """Generate cache key for token introspection."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        return f"introspect:{token_hash}"

    async def _get_cached_introspection(self, token: str) -> bool | None:
        """Get cached introspection result from Redis."""
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return None

        try:
            cached = await redis_client.get(self._cache_key(token))
            if cached is not None:
                return cached == "1"
        except Exception as e:
            logger.warning("Redis cache read error: %s", e)

        return None

    async def _cache_introspection(self, token: str, is_active: bool) -> None:
        """Cache introspection result in Redis."""
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

    async def introspect_token(self, token: str) -> bool:
        """Check if a token is active via OAuth2 token introspection (RFC 7662)."""
        # Check cache first
        cached = await self._get_cached_introspection(token)
        if cached is not None:
            logger.debug("Token introspection cache hit: active=%s", cached)
            return cached

        try:
            client = await self._get_http_client()
            response = await client.post(
                self.introspection_uri,
                data={
                    "token": token,
                    "token_type_hint": "access_token",
                    "client_id": settings.oauth2_client_id,
                    "client_secret": settings.oauth2_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            result = response.json()

            is_active = result.get("active", False)
            await self._cache_introspection(token, is_active)

            logger.debug("Token introspection result: active=%s", is_active)
            return is_active

        except Exception as e:
            logger.warning("Token introspection failed: %s", e)
            return True

    async def validate_token_with_introspection(self, token: str) -> dict[str, Any]:
        """Validate JWT token with introspection check."""
        claims = await self.validate_token(token)

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


# Global validator instance
jwt_validator = JWTValidator()
