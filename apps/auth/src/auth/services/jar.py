# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWT Authorization Request (JAR) service (RFC 9101)."""

import logging
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient, PyJWKClientError

from auth.db.models.oauth2 import OAuth2Client

logger = logging.getLogger(__name__)

# Supported signing algorithms for JAR
SUPPORTED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

# Cache for JWKS clients (keyed by jwks_uri)
_jwks_clients: dict[str, tuple[PyJWKClient, float]] = {}
JWKS_CACHE_TTL = 300  # 5 minutes


class JARError(Exception):
    """JAR validation error."""

    def __init__(self, error: str, description: str):
        self.error = error
        self.description = description
        super().__init__(description)


class JARService:
    """Service for validating JWT Authorization Requests (RFC 9101)."""

    def _get_jwks_client(self, jwks_uri: str) -> PyJWKClient:
        """Get or create a cached JWKS client for the given URI.

        Args:
            jwks_uri: The JWKS URI to fetch keys from.

        Returns:
            A PyJWKClient instance.
        """
        now = time.time()

        # Check cache
        if jwks_uri in _jwks_clients:
            client, cached_at = _jwks_clients[jwks_uri]
            if now - cached_at < JWKS_CACHE_TTL:
                return client

        # Create new client
        client = PyJWKClient(jwks_uri)
        _jwks_clients[jwks_uri] = (client, now)
        return client

    async def fetch_client_jwks(self, jwks_uri: str) -> dict[str, Any]:
        """Fetch JWKS from client's jwks_uri.

        Args:
            jwks_uri: The JWKS URI to fetch from.

        Returns:
            The JWKS as a dictionary.

        Raises:
            JARError: If JWKS fetch fails.
        """
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(jwks_uri, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise JARError(
                "invalid_request",
                f"Failed to fetch client JWKS: {e}",
            )
        except Exception as e:
            raise JARError(
                "invalid_request",
                f"Failed to parse client JWKS: {e}",
            )

    def validate_request_object(
        self,
        request_jwt: str,
        client: OAuth2Client,
        expected_issuer: str | None = None,
        expected_audience: str | None = None,
    ) -> dict[str, Any]:
        """Validate a JWT Authorization Request object.

        Args:
            request_jwt: The JWT request object.
            client: The OAuth2 client.
            expected_issuer: Expected issuer (client_id).
            expected_audience: Expected audience (authorization server issuer).

        Returns:
            The validated claims from the JWT.

        Raises:
            JARError: If validation fails.
        """
        # Check if client has JWKS URI configured
        if not client.jwks_uri:
            logger.warning("JAR validation failed: no jwks_uri for client %s", client.client_id)
            raise JARError(
                "invalid_request",
                "Client has no jwks_uri configured for JAR",
            )

        # Get the expected algorithm
        expected_alg = client.request_object_signing_alg or "RS256"
        if expected_alg not in SUPPORTED_ALGORITHMS:
            logger.warning(
                "JAR validation failed: unsupported algorithm %s for client %s",
                expected_alg,
                client.client_id,
            )
            raise JARError(
                "invalid_request",
                f"Unsupported signing algorithm: {expected_alg}",
            )

        try:
            # Get the signing key from client's JWKS
            jwks_client = self._get_jwks_client(client.jwks_uri)
            signing_key = jwks_client.get_signing_key_from_jwt(request_jwt)

            # Decode and validate the JWT
            claims = jwt.decode(
                request_jwt,
                signing_key.key,
                algorithms=[expected_alg],
                options={
                    "require": ["iss", "aud", "exp"],
                    "verify_exp": True,
                    "verify_iss": expected_issuer is not None,
                    "verify_aud": expected_audience is not None,
                },
                issuer=expected_issuer,
                audience=expected_audience,
            )

            logger.info("JAR request validated for client %s", client.client_id)
            return claims

        except PyJWKClientError as e:
            logger.warning(
                "JAR validation failed: JWKS error for client %s: %s", client.client_id, e
            )
            raise JARError(
                "invalid_request",
                f"Failed to get signing key from JWKS: {e}",
            )
        except jwt.ExpiredSignatureError:
            logger.warning("JAR validation failed: expired for client %s", client.client_id)
            raise JARError(
                "invalid_request",
                "Request object has expired",
            )
        except jwt.InvalidIssuerError:
            logger.warning("JAR validation failed: invalid issuer for client %s", client.client_id)
            raise JARError(
                "invalid_request",
                "Invalid issuer in request object",
            )
        except jwt.InvalidAudienceError:
            logger.warning(
                "JAR validation failed: invalid audience for client %s", client.client_id
            )
            raise JARError(
                "invalid_request",
                "Invalid audience in request object",
            )
        except jwt.InvalidSignatureError:
            logger.warning(
                "JAR validation failed: invalid signature for client %s", client.client_id
            )
            raise JARError(
                "invalid_request",
                "Invalid signature on request object",
            )
        except jwt.DecodeError as e:
            logger.warning(
                "JAR validation failed: decode error for client %s: %s", client.client_id, e
            )
            raise JARError(
                "invalid_request",
                f"Failed to decode request object: {e}",
            )
        except Exception as e:
            logger.warning("JAR validation failed for client %s: %s", client.client_id, e)
            raise JARError(
                "invalid_request",
                f"Request object validation failed: {e}",
            )

    def extract_authorization_params(
        self,
        claims: dict[str, Any],
        client: OAuth2Client,
    ) -> dict[str, Any]:
        """Extract authorization parameters from JAR claims.

        Args:
            claims: The validated JWT claims.
            client: The OAuth2 client.

        Returns:
            Dictionary of authorization parameters.

        Raises:
            JARError: If required parameters are missing or invalid.
        """
        # Required parameters
        response_type = claims.get("response_type")
        if not response_type:
            raise JARError(
                "invalid_request",
                "response_type is required in request object",
            )

        redirect_uri = claims.get("redirect_uri")
        if not redirect_uri:
            raise JARError(
                "invalid_request",
                "redirect_uri is required in request object",
            )

        # Validate client_id matches
        jar_client_id = claims.get("client_id")
        if jar_client_id and jar_client_id != client.client_id:
            raise JARError(
                "invalid_request",
                "client_id in request object does not match",
            )

        # Extract optional parameters
        scope = claims.get("scope")
        scopes = scope.split() if scope else ["openid"]

        return {
            "response_type": response_type,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "state": claims.get("state"),
            "nonce": claims.get("nonce"),
            "code_challenge": claims.get("code_challenge"),
            "code_challenge_method": claims.get("code_challenge_method"),
            "prompt": claims.get("prompt"),
        }
