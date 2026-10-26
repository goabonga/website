# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""HTTP client for VPN Portal API."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

from internal.config import settings

logger = logging.getLogger(__name__)


class VPNSession(BaseModel):
    """VPN session information (matches vpn-portal AdminSessionResponse)."""

    id: str
    user_id: str
    username: str
    device_name: str | None
    connected_at: datetime
    assigned_ip: str
    certificate_serial: str
    expires_at: datetime
    scopes: list[str]
    routes: list[str]


class VPNSessionsResponse(BaseModel):
    """Response from list sessions endpoint."""

    sessions: list[VPNSession]
    total: int
    page: int
    per_page: int


class VPNPortalClient:
    """HTTP client to interact with VPN Portal API."""

    def __init__(self) -> None:
        self._base_url = (
            settings.vpn_portal_api_url.rstrip("/") if settings.vpn_portal_api_url else ""
        )
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._issuer = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def _get_access_token(self) -> str:
        """Get access token using client credentials flow with vpn:admin scope."""
        # Return cached token if still valid
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now(UTC) < self._token_expires_at - timedelta(seconds=30)
        ):
            return self._access_token

        if not self._issuer:
            raise ValueError("oauth2_issuer not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._issuer}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "vpn:admin",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return self._access_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated request to the VPN Portal API."""
        if not self._base_url:
            raise ValueError("vpn_portal_api_url not configured")

        try:
            token = await self._get_access_token()
        except Exception as e:
            logger.error("Failed to get access token for VPN Portal API: %s", e)
            raise

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self._base_url}{endpoint}",
                params=params,
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()

    async def get_sessions(
        self,
        page: int = 1,
        per_page: int = 50,
    ) -> VPNSessionsResponse | None:
        """Get VPN sessions (active only - non-revoked, not expired).

        Args:
            page: Page number (1-indexed).
            per_page: Number of sessions per page.

        Returns:
            VPNSessionsResponse object or None on error.
        """
        try:
            data = await self._request(
                "GET",
                "/api/v1/admin/sessions",
                params={"page": page, "per_page": per_page},
            )
            return VPNSessionsResponse(**data)
        except Exception as e:
            logger.exception("Failed to fetch VPN sessions: %s", e)
            return None

    async def revoke_session(self, serial_number: str) -> bool:
        """Revoke a VPN session by certificate serial number.

        Args:
            serial_number: The certificate serial number to revoke.

        Returns:
            True if revocation was successful, False otherwise.
        """
        try:
            await self._request(
                "DELETE",
                f"/api/v1/admin/sessions/{serial_number}",
            )
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Session not found for revocation: %s", serial_number)
            else:
                logger.exception("Failed to revoke session: %s", e)
            return False
        except Exception as e:
            logger.exception("Failed to revoke session: %s", e)
            return False


# Singleton instance
vpn_portal_client = VPNPortalClient()
