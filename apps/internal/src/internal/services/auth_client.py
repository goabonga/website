# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""HTTP client for auth API (auth.goabonga.com)."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from internal.config import settings

logger = logging.getLogger(__name__)


class UserInfo(BaseModel):
    """User information from auth API."""

    id: uuid.UUID
    email: str | None = None
    name: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


class AuthClient:
    """HTTP client to interact with auth API."""

    def __init__(self) -> None:
        self._base_url = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def _get_access_token(self) -> str:
        """Get access token using client credentials flow."""
        # Return cached token if still valid
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now(UTC) < self._token_expires_at - timedelta(seconds=30)
        ):
            return self._access_token

        if not self._base_url:
            raise ValueError("oauth2_issuer not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "users:read",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return self._access_token

    async def get_user(self, user_id: uuid.UUID) -> UserInfo | None:
        """Fetch user information by ID from auth API.

        Args:
            user_id: The UUID of the user to fetch.

        Returns:
            UserInfo object if found, None otherwise.
        """
        if not self._base_url:
            return None

        try:
            token = await self._get_access_token()
            logger.debug(
                "Got access token for auth API (first 20 chars): %s...",
                token[:20] if token else None,
            )
        except Exception as e:
            logger.error("Failed to get access token for auth API: %s", e)
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._base_url}/admin/api/users/{user_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )

            if response.status_code == 404:
                logger.debug("User %s not found in auth API", user_id)
                return None

            if response.status_code != 200:
                logger.error(
                    "Auth API returned %s for user %s: %s",
                    response.status_code,
                    user_id,
                    response.text,
                )
                return None

            data = response.json()
            logger.debug("Auth API response for user %s: %s", user_id, data)

            # Response is wrapped in {"user": {...}}
            user_data = data.get("user", data)

            return UserInfo(
                id=uuid.UUID(user_data["id"]),
                email=user_data.get("email"),
                name=user_data.get("profile", {}).get("name") if user_data.get("profile") else None,
                is_active=user_data.get("is_active", True),
                created_at=datetime.fromisoformat(user_data["created_at"].replace("Z", "+00:00"))
                if user_data.get("created_at")
                else None,
            )
        except Exception as e:
            logger.exception("Failed to fetch user %s from auth API: %s", user_id, e)
            return None


# Singleton instance
auth_client = AuthClient()
