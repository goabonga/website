# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Synchronous HTTP client for analytics API (for Celery tasks)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel

from internal.config import settings

logger = logging.getLogger(__name__)


class CampaignCreateResponse(BaseModel):
    """Campaign creation response."""

    id: UUID
    name: str
    description: str | None
    tracking_key: str
    destination_url: str | None
    is_active: bool
    created_at: datetime


class PixelCreateResponse(BaseModel):
    """Pixel creation response."""

    id: UUID
    pixel_key: str
    campaign_id: UUID
    recipient_email: str | None
    recipient_id: str | None
    created_at: datetime


class CampaignDetailResponse(BaseModel):
    """Campaign detail response with stats."""

    id: UUID
    name: str
    description: str | None
    tracking_key: str
    destination_url: str | None
    is_active: bool
    click_count: int
    unique_click_count: int
    created_at: datetime
    updated_at: datetime


class PixelStatsResponse(BaseModel):
    """Pixel stats response."""

    id: UUID
    pixel_key: str
    recipient_email: str | None
    recipient_id: str | None
    open_count: int
    first_opened_at: datetime | None
    last_opened_at: datetime | None
    created_at: datetime


class SyncAnalyticsClient:
    """Synchronous HTTP client for analytics API (for Celery tasks)."""

    def __init__(self) -> None:
        self._base_url = settings.analytics_api_url.rstrip("/")
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._issuer = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        # Cache tokens per scope
        self._tokens: dict[str, tuple[str, datetime]] = {}

    def _get_access_token(self, scope: str = "analytics:write") -> str:
        """Get access token using client credentials flow."""
        # Return cached token if still valid
        if scope in self._tokens:
            token, expires_at = self._tokens[scope]
            if datetime.now(UTC) < expires_at - timedelta(seconds=30):
                return token

        if not self._issuer:
            raise ValueError("oauth2_issuer not configured")

        with httpx.Client() as client:
            response = client.post(
                f"{self._issuer}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self._tokens[scope] = (access_token, expires_at)
        return access_token

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        scope: str = "analytics:write",
    ) -> Any:
        """Make an authenticated request to the analytics API."""
        if not self._base_url:
            logger.warning("analytics_api_url not configured, skipping analytics")
            return {}

        try:
            token = self._get_access_token(scope=scope)
        except Exception as e:
            logger.error("Failed to get access token for analytics API: %s", e)
            raise

        with httpx.Client() as client:
            response = client.request(
                method,
                f"{self._base_url}{endpoint}",
                params=params,
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()

    def create_campaign(
        self,
        name: str,
        description: str | None = None,
        destination_url: str | None = None,
        extra_data: dict | None = None,
    ) -> CampaignCreateResponse | None:
        """Create a new analytics campaign for email tracking.

        Args:
            name: Campaign name.
            description: Campaign description.
            destination_url: URL to redirect link clicks to.
            extra_data: Additional metadata.

        Returns:
            CampaignCreateResponse object or None on error.
        """
        try:
            data = self._request(
                "POST",
                "/api/v1/stats/campaigns",
                json_data={
                    "name": name,
                    "description": description,
                    "destination_url": destination_url,
                    "extra_data": extra_data,
                },
            )
            if not data:
                return None
            return CampaignCreateResponse(**data)
        except Exception as e:
            logger.exception("Failed to create analytics campaign: %s", e)
            return None

    def create_pixel(
        self,
        campaign_id: UUID,
        recipient_email: str | None = None,
        recipient_id: str | None = None,
        extra_data: dict | None = None,
    ) -> PixelCreateResponse | None:
        """Create a tracking pixel for an email recipient.

        Args:
            campaign_id: Parent campaign ID.
            recipient_email: Recipient email address.
            recipient_id: Custom recipient identifier.
            extra_data: Additional metadata.

        Returns:
            PixelCreateResponse object or None on error.
        """
        try:
            data = self._request(
                "POST",
                f"/api/v1/stats/campaigns/{campaign_id}/pixels",
                json_data={
                    "recipient_email": recipient_email,
                    "recipient_id": recipient_id,
                    "extra_data": extra_data,
                },
            )
            if not data:
                return None
            return PixelCreateResponse(**data)
        except Exception as e:
            logger.exception("Failed to create analytics pixel: %s", e)
            return None

    def create_pixels_batch(
        self,
        campaign_id: UUID,
        pixels: list[dict],
    ) -> list[PixelCreateResponse]:
        """Create multiple tracking pixels at once.

        Args:
            campaign_id: Parent campaign ID.
            pixels: List of pixel data dicts with recipient_email, recipient_id, extra_data.

        Returns:
            List of created PixelCreateResponse objects.
        """
        try:
            data = self._request(
                "POST",
                f"/api/v1/stats/campaigns/{campaign_id}/pixels/batch",
                json_data={"pixels": pixels},
            )
            if not data:
                return []
            return [PixelCreateResponse(**p) for p in data.get("pixels", [])]
        except Exception as e:
            logger.exception("Failed to create analytics pixels batch: %s", e)
            return []

    def get_campaign_detail(
        self,
        campaign_id: UUID,
        days: int = 30,
    ) -> CampaignDetailResponse | None:
        """Get detailed campaign statistics.

        Args:
            campaign_id: Campaign ID.
            days: Number of days for stats (default 30).

        Returns:
            CampaignDetailResponse object or None on error.
        """
        try:
            data = self._request(
                "GET",
                f"/api/v1/stats/campaigns/{campaign_id}",
                params={"days": days},
                scope="analytics:read",
            )
            if not data:
                return None
            return CampaignDetailResponse(**data)
        except Exception as e:
            logger.error("Failed to get campaign detail: %s", e)
            return None

    def get_campaign_pixels(
        self,
        campaign_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PixelStatsResponse]:
        """Get pixels for a campaign with their open stats.

        Args:
            campaign_id: Campaign ID.
            limit: Maximum pixels to return.
            offset: Pagination offset.

        Returns:
            List of PixelStatsResponse objects.
        """
        try:
            data = self._request(
                "GET",
                f"/api/v1/stats/campaigns/{campaign_id}/pixels",
                params={"limit": limit, "offset": offset},
                scope="analytics:read",
            )
            if not data:
                return []
            return [PixelStatsResponse(**p) for p in data]
        except Exception as e:
            logger.error("Failed to get campaign pixels: %s", e)
            return []


def get_sync_analytics_client() -> SyncAnalyticsClient:
    """Get a sync analytics client instance."""
    return SyncAnalyticsClient()
