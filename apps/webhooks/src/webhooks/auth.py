# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 client_credentials token acquisition.

Acquires and caches an access token for authenticating with downstream
services (mailler, billing) using the OAuth2 client_credentials grant.
"""

import time

import httpx

from webhooks.config import settings
from webhooks.logging import get_logger

logger = get_logger(__name__)

_REFRESH_MARGIN = 30  # Refresh token this many seconds before expiry


class OAuth2ClientCredentials:
    """Acquires and caches an OAuth2 access token using client_credentials grant."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0

    @property
    def is_configured(self) -> bool:
        return bool(
            settings.oauth2_token_url
            and settings.oauth2_client_id
            and settings.oauth2_client_secret
        )

    async def get_token(self) -> str | None:
        """Get a valid access token, refreshing if needed.

        Returns:
            The access token string, or None if not configured or on failure.
        """
        if not self.is_configured:
            return None

        now = time.monotonic()
        if self._token and now < self._expires_at - _REFRESH_MARGIN:
            return self._token

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.oauth2_token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.oauth2_client_id,
                        "client_secret": settings.oauth2_client_secret,
                        "scope": "mailler:webhooks billing:webhooks",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if response.status_code != 200:
                logger.error(
                    "Failed to acquire OAuth2 token | status=%d body=%s",
                    response.status_code,
                    response.text[:200],
                )
                if self._token and now < self._expires_at:
                    logger.warning("Using stale OAuth2 token")
                    return self._token
                return None

            data = response.json()
            self._token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._expires_at = now + expires_in

            logger.info("OAuth2 token acquired | expires_in=%d", expires_in)
            return self._token

        except Exception as e:
            logger.error("Error acquiring OAuth2 token: %s", e)
            if self._token and now < self._expires_at:
                logger.warning("Using stale OAuth2 token after error")
                return self._token
            return None


oauth2_client = OAuth2ClientCredentials()


async def get_authorization_header(static_token: str = "") -> str | None:
    """Get an Authorization header value, preferring OAuth2 over static token.

    Args:
        static_token: Legacy static token (fallback during transition).

    Returns:
        The full header value (e.g., "Bearer xxx"), or None.
    """
    token = await oauth2_client.get_token()
    if token:
        return f"Bearer {token}"

    if static_token:
        return f"Bearer {static_token}"

    return None
