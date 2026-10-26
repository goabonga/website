# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWKS (JSON Web Key Set) fetching and caching with OIDC discovery."""

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient, PyJWKClientError

from reachy_mini_api.config import settings
from reachy_mini_api.logging import get_logger

logger = get_logger(__name__)


class JWKSManager:
    """Manage JWKS fetching and caching for JWT validation.

    Uses OIDC discovery to dynamically resolve JWKS URI and supports
    multiple trusted issuers.
    """

    def __init__(self) -> None:
        self._jwks_client: PyJWKClient | None = None
        self._issuer_config: dict[str, Any] | None = None
        self._config_fetched_at: float = 0
        self._http_client: httpx.AsyncClient | None = None

    @property
    def issuer(self) -> str:
        """Get the primary OAuth2 issuer URL."""
        return settings.oauth2_issuer.rstrip("/")

    @property
    def accepted_issuers(self) -> list[str]:
        """Get list of all accepted issuers (primary + trusted)."""
        trusted = [i.strip() for i in settings.oauth2_trusted_issuers.split(",") if i.strip()]
        issuers = [self.issuer] + trusted if self.issuer else trusted
        return issuers

    @property
    def is_configured(self) -> bool:
        """Check if OAuth2 is configured."""
        return bool(settings.oauth2_issuer)

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def fetch_issuer_config(self) -> dict[str, Any]:
        """Fetch OIDC discovery document from issuer."""
        if not self.is_configured:
            raise ValueError("OAuth2 issuer not configured")

        now = time.time()
        if (
            self._issuer_config is not None
            and (now - self._config_fetched_at) < settings.jwks_cache_ttl
        ):
            return self._issuer_config

        client = await self._get_http_client()
        response = await client.get(f"{self.issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        self._issuer_config = response.json()
        self._config_fetched_at = now
        return self._issuer_config

    def _get_jwks_client(self, jwks_uri: str) -> PyJWKClient:
        """Get or create JWKS client."""
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                jwks_uri,
                cache_jwk_set=True,
                lifespan=settings.jwks_cache_ttl,
            )
        return self._jwks_client

    async def validate_token(self, token: str) -> dict[str, Any]:
        """Validate a JWT token and return its claims.

        Args:
            token: The JWT access token to validate

        Returns:
            Dictionary of token claims

        Raises:
            jwt.InvalidTokenError: If token is invalid
            ValueError: If OAuth2 is not configured
        """
        if not self.is_configured:
            raise ValueError("OAuth2 issuer not configured")

        config = await self.fetch_issuer_config()
        jwks_uri = config.get("jwks_uri")
        if not jwks_uri:
            raise ValueError("JWKS URI not found in issuer config")

        jwks_client = self._get_jwks_client(jwks_uri)

        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientError as e:
            raise jwt.InvalidTokenError(f"Failed to get signing key: {e}")

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=self.accepted_issuers,
            options={
                "verify_aud": False,
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
            },
        )
        return claims

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None


# Global JWKS manager instance
jwks_manager = JWKSManager()
