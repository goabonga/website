# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 client credentials for the calls to the platform services.

Billing, mailler and the custom domain service all authenticate this application with
a bearer token obtained from the OAuth2 server of the platform (``OAUTH2_ISSUER``) with
the client credentials grant. Each service can have its own OAuth2 client
(``<SERVICE>_CLIENT_ID``/``<SERVICE>_CLIENT_SECRET``); an empty value falls back to the
confidential client of the application (``OAUTH2_CLIENT_ID``/``OAUTH2_CLIENT_SECRET``).
The services identify this application by the ``client_id`` of the token, so the client
used for a service must be the one registered there.
"""

import time
from dataclasses import dataclass

import httpx

from knowledge.config import get_settings
from knowledge.logging import get_logger

logger = get_logger(__name__)

# A token is renewed this long before it expires.
EXPIRY_MARGIN_SECONDS = 30
# Lifetime assumed when the token response does not say.
DEFAULT_LIFETIME_SECONDS = 300


class ServiceAuthError(Exception):
    """A token for a platform service could not be obtained.

    ``retryable`` is true when asking again later can work (the OAuth2 server is
    unreachable or failing) and false when the configuration has to change.
    """

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ClientCredentials:
    """The OAuth2 client used to call one platform service."""

    client_id: str
    client_secret: str


def credentials_for(service: str) -> ClientCredentials:
    """Return the OAuth2 client of a service (``billing``, ``mailler``, ``custom_domain``)."""
    settings = get_settings()
    client_id = getattr(settings, f"{service}_client_id", "") or settings.oauth2_client_id
    client_secret = (
        getattr(settings, f"{service}_client_secret", "") or settings.oauth2_client_secret
    )
    return ClientCredentials(client_id=client_id, client_secret=client_secret)


def token_url() -> str:
    """Return the token endpoint of the OAuth2 server."""
    issuer = get_settings().oauth2_issuer.rstrip("/")
    if not issuer:
        raise ServiceAuthError("OAUTH2_ISSUER is not configured")
    return f"{issuer}/oauth2/token"


def _token_request(credentials: ClientCredentials, scope: str) -> dict[str, str]:
    if not credentials.client_id or not credentials.client_secret:
        raise ServiceAuthError("OAuth2 client credentials are not configured")
    return {
        "grant_type": "client_credentials",
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scope": scope,
    }


def _read_token(response: httpx.Response) -> tuple[str, float]:
    if response.status_code != 200:
        logger.error("OAuth2 token request refused: %s", response.status_code)
        raise ServiceAuthError(
            f"OAuth2 token request failed: {response.status_code}",
            retryable=response.status_code >= 500,
        )
    try:
        body = response.json()
        token = body["access_token"]
    except (ValueError, KeyError, TypeError) as error:
        raise ServiceAuthError("OAuth2 token response is not valid") from error
    lifetime = body.get("expires_in", DEFAULT_LIFETIME_SECONDS)
    return token, time.monotonic() + float(lifetime) - EXPIRY_MARGIN_SECONDS


class TokenCache:
    """Client credentials tokens by client and scope, renewed shortly before they expire."""

    def __init__(self) -> None:
        self._tokens: dict[tuple[str, str], tuple[str, float]] = {}

    def clear(self) -> None:
        """Forget every token, for instance after the service refused one."""
        self._tokens.clear()

    def _cached(self, credentials: ClientCredentials, scope: str) -> str | None:
        entry = self._tokens.get((credentials.client_id, scope))
        if entry and time.monotonic() < entry[1]:
            return entry[0]
        return None

    def get(self, credentials: ClientCredentials, scope: str) -> str:
        """Return a valid token for ``scope`` (synchronous, for the Celery tasks)."""
        cached = self._cached(credentials, scope)
        if cached:
            return cached
        data = _token_request(credentials, scope)
        try:
            with httpx.Client(timeout=get_settings().service_timeout) as client:
                response = client.post(token_url(), data=data)
        except httpx.RequestError as error:
            raise ServiceAuthError(
                f"OAuth2 token request failed: {error}", retryable=True
            ) from error
        token, expires_at = _read_token(response)
        self._tokens[(credentials.client_id, scope)] = (token, expires_at)
        return token

    async def aget(self, credentials: ClientCredentials, scope: str) -> str:
        """Return a valid token for ``scope`` (asynchronous, for the web routes)."""
        cached = self._cached(credentials, scope)
        if cached:
            return cached
        data = _token_request(credentials, scope)
        try:
            async with httpx.AsyncClient(timeout=get_settings().service_timeout) as client:
                response = await client.post(token_url(), data=data)
        except httpx.RequestError as error:
            raise ServiceAuthError(
                f"OAuth2 token request failed: {error}", retryable=True
            ) from error
        token, expires_at = _read_token(response)
        self._tokens[(credentials.client_id, scope)] = (token, expires_at)
        return token
