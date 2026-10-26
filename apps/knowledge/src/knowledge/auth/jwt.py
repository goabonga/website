# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWT validation with JWKS and introspection."""

import logging
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from knowledge.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class JWTValidationError(Exception):
    """JWT validation failed."""

    pass


class JWTValidator:
    """Validates JWT tokens using JWKS and optional introspection."""

    def __init__(self) -> None:
        self.issuer = settings.oauth2_issuer
        self._jwks_client: PyJWKClient | None = None
        self._http_client: httpx.AsyncClient | None = None

    @property
    def jwks_client(self) -> PyJWKClient:
        """Get or create JWKS client with caching."""
        if self._jwks_client is None:
            jwks_uri = f"{self.issuer}/.well-known/jwks.json"
            self._jwks_client = PyJWKClient(
                jwks_uri,
                cache_keys=True,
                lifespan=3600,  # Cache keys for 1 hour
            )
        return self._jwks_client

    async def get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token signature and claims.

        Args:
            token: The JWT token to validate.

        Returns:
            The decoded token claims.

        Raises:
            JWTValidationError: If validation fails.
        """
        if not self.issuer:
            raise JWTValidationError("OAuth2 issuer not configured")

        try:
            # Get the signing key from JWKS
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)

            # Decode and validate the token
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=self.issuer,
                options={
                    "verify_aud": False,  # Audience validation is optional
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "require": ["sub", "exp", "iat"],
                },
            )
            return claims

        except jwt.ExpiredSignatureError:
            raise JWTValidationError("Token has expired")
        except jwt.InvalidIssuerError:
            raise JWTValidationError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise JWTValidationError(f"Invalid token: {e}")
        except Exception as e:
            logger.error(f"JWT validation error: {e}")
            raise JWTValidationError(f"Token validation failed: {e}")

    async def introspect_token(self, token: str) -> bool:
        """Check if token is active via introspection endpoint (RFC 7662).

        Args:
            token: The token to introspect.

        Returns:
            True if token is active, False otherwise.
        """
        if not self.issuer:
            return False

        if not settings.oauth2_client_id or not settings.oauth2_client_secret:
            # No credentials for introspection, skip
            logger.debug("Skipping introspection: no client credentials")
            return True

        try:
            client = await self.get_http_client()
            response = await client.post(
                f"{self.issuer}/oauth2/introspect",
                data={
                    "token": token,
                    "token_type_hint": "access_token",
                },
                auth=(settings.oauth2_client_id, settings.oauth2_client_secret),
            )

            if response.status_code != 200:
                logger.warning(f"Introspection failed: {response.status_code}")
                # Graceful degradation: allow token if introspection fails
                return True

            data = response.json()
            return data.get("active", False)

        except Exception as e:
            logger.error(f"Introspection error: {e}")
            # Graceful degradation: allow token if introspection fails
            return True

    async def fetch_userinfo(self, token: str) -> dict[str, Any]:
        """Fetch user info from the userinfo endpoint.

        Args:
            token: The access token.

        Returns:
            User info claims (name, email, etc.).
        """
        if not self.issuer:
            return {}

        try:
            client = await self.get_http_client()
            response = await client.get(
                f"{self.issuer}/userinfo",
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code == 200:
                return response.json()

            logger.debug(f"Userinfo request failed: {response.status_code}")
            return {}

        except Exception as e:
            logger.warning(f"Failed to fetch userinfo: {e}")
            return {}

    async def validate_token_with_introspection(
        self, token: str, check_revocation: bool = True, fetch_userinfo: bool = False
    ) -> dict[str, Any]:
        """Validate token and optionally check for revocation.

        Args:
            token: The JWT token to validate.
            check_revocation: Whether to check token revocation via introspection.
            fetch_userinfo: Whether to fetch additional user info from userinfo endpoint.

        Returns:
            The decoded token claims (merged with userinfo if requested).

        Raises:
            JWTValidationError: If validation fails or token is revoked.
        """
        # First validate the JWT signature and claims
        claims = self.validate_token(token)

        # Then check if token is revoked
        if check_revocation:
            is_active = await self.introspect_token(token)
            if not is_active:
                raise JWTValidationError("Token has been revoked")

        # Optionally fetch userinfo for additional claims (name, email, etc.)
        if fetch_userinfo:
            userinfo = await self.fetch_userinfo(token)
            claims.update(userinfo)

        return claims

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


# Singleton instance
_jwt_validator: JWTValidator | None = None


def get_jwt_validator() -> JWTValidator:
    """Get or create the JWT validator singleton."""
    global _jwt_validator
    if _jwt_validator is None:
        _jwt_validator = JWTValidator()
    return _jwt_validator
