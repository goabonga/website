# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""HTTP client for analytics API (ua.goabonga.com)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel

from internal.config import settings

logger = logging.getLogger(__name__)


class OverviewStats(BaseModel):
    """Overview statistics from analytics."""

    total_sessions: int
    unique_visitors: int
    total_pageviews: int
    total_events: int
    period_start: datetime
    period_end: datetime


class DailyStats(BaseModel):
    """Daily statistics."""

    date: str
    sessions: int
    pageviews: int
    unique_visitors: int


class CountryStats(BaseModel):
    """Statistics by country."""

    country: str | None
    sessions: int
    percentage: float


class DeviceStats(BaseModel):
    """Statistics by device type."""

    device_type: str | None
    sessions: int
    percentage: float


class BrowserStats(BaseModel):
    """Statistics by browser."""

    browser: str | None
    sessions: int
    percentage: float


class ReferrerStats(BaseModel):
    """Statistics by referrer."""

    referrer: str | None
    sessions: int
    percentage: float


class PageStats(BaseModel):
    """Statistics by page."""

    page_url: str | None
    pageviews: int
    unique_sessions: int


class EventStats(BaseModel):
    """Statistics by event type."""

    event_type: str
    count: int
    unique_sessions: int


class CampaignStats(BaseModel):
    """Campaign statistics."""

    id: UUID
    name: str
    tracking_key: str
    is_active: bool
    click_count: int
    unique_click_count: int
    pixel_count: int
    total_opens: int
    created_at: datetime


class CampaignDetail(BaseModel):
    """Detailed campaign statistics."""

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
    clicks_by_day: list[DailyStats]
    clicks_by_country: list[CountryStats]


class PixelStats(BaseModel):
    """Pixel statistics."""

    id: UUID
    pixel_key: str
    recipient_email: str | None
    recipient_id: str | None
    open_count: int
    first_opened_at: datetime | None
    last_opened_at: datetime | None
    created_at: datetime


class IPStats(BaseModel):
    """Statistics by IP address."""

    ip_address: str
    sessions: int
    pageviews: int
    countries: list[str]
    browsers: list[str]
    device_types: list[str]
    first_seen: datetime
    last_seen: datetime


class IPPageStats(BaseModel):
    """Page statistics for an IP address."""

    page_url: str | None
    pageviews: int


class IPEventStats(BaseModel):
    """Event statistics for an IP address."""

    event_type: str
    count: int


class IPDetailStats(BaseModel):
    """Detailed statistics for a specific IP address."""

    ip_address: str
    total_sessions: int
    total_pageviews: int
    total_events: int
    countries: list[str]
    cities: list[str]
    browsers: list[str]
    device_types: list[str]
    operating_systems: list[str]
    referrers: list[str]
    first_seen: datetime
    last_seen: datetime
    sessions_by_day: list[DailyStats]
    pages: list[IPPageStats] = []
    events: list[IPEventStats] = []


class CampaignCreate(BaseModel):
    """Campaign creation response."""

    id: UUID
    name: str
    description: str | None
    tracking_key: str
    destination_url: str | None
    is_active: bool
    created_at: datetime


class PixelCreate(BaseModel):
    """Pixel creation response."""

    id: UUID
    pixel_key: str
    campaign_id: UUID
    recipient_email: str | None
    recipient_id: str | None
    created_at: datetime


class AnalyticsClient:
    """HTTP client to interact with analytics API."""

    def __init__(self) -> None:
        self._base_url = settings.analytics_api_url.rstrip("/")
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._issuer = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        # Cache tokens per scope
        self._tokens: dict[str, tuple[str, datetime]] = {}

    async def _get_access_token(self, scope: str = "analytics:read") -> str:
        """Get access token using client credentials flow."""
        # Return cached token if still valid
        if scope in self._tokens:
            token, expires_at = self._tokens[scope]
            if datetime.now(UTC) < expires_at - timedelta(seconds=30):
                return token

        if not self._issuer:
            raise ValueError("oauth2_issuer not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
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

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        scope: str = "analytics:read",
    ) -> Any:
        """Make an authenticated request to the analytics API."""
        if not self._base_url:
            raise ValueError("analytics_api_url not configured")

        try:
            token = await self._get_access_token(scope=scope)
        except Exception as e:
            logger.error("Failed to get access token for analytics API: %s", e)
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
            return response.json()

    async def get_overview(self, days: int = 30) -> OverviewStats | None:
        """Get overview statistics.

        Args:
            days: Number of days to include in the statistics.

        Returns:
            OverviewStats object or None on error.
        """
        try:
            data = await self._request("GET", "/api/v1/stats/overview", {"days": days})
            return OverviewStats(**data)
        except Exception as e:
            logger.exception("Failed to fetch overview stats: %s", e)
            return None

    async def get_daily_stats(self, days: int = 30) -> list[DailyStats]:
        """Get daily statistics.

        Args:
            days: Number of days to include.

        Returns:
            List of DailyStats objects.
        """
        try:
            data = await self._request("GET", "/api/v1/stats/daily", {"days": days})
            return [DailyStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch daily stats: %s", e)
            return []

    async def get_country_stats(self, days: int = 30, limit: int = 10) -> list[CountryStats]:
        """Get statistics by country.

        Args:
            days: Number of days to include.
            limit: Maximum number of countries to return.

        Returns:
            List of CountryStats objects.
        """
        try:
            data = await self._request(
                "GET", "/api/v1/stats/countries", {"days": days, "limit": limit}
            )
            return [CountryStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch country stats: %s", e)
            return []

    async def get_device_stats(self, days: int = 30) -> list[DeviceStats]:
        """Get statistics by device type.

        Args:
            days: Number of days to include.

        Returns:
            List of DeviceStats objects.
        """
        try:
            data = await self._request("GET", "/api/v1/stats/devices", {"days": days})
            return [DeviceStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch device stats: %s", e)
            return []

    async def get_browser_stats(self, days: int = 30, limit: int = 10) -> list[BrowserStats]:
        """Get statistics by browser.

        Args:
            days: Number of days to include.
            limit: Maximum number of browsers to return.

        Returns:
            List of BrowserStats objects.
        """
        try:
            data = await self._request(
                "GET", "/api/v1/stats/browsers", {"days": days, "limit": limit}
            )
            return [BrowserStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch browser stats: %s", e)
            return []

    async def get_referrer_stats(self, days: int = 30, limit: int = 10) -> list[ReferrerStats]:
        """Get statistics by referrer.

        Args:
            days: Number of days to include.
            limit: Maximum number of referrers to return.

        Returns:
            List of ReferrerStats objects.
        """
        try:
            data = await self._request(
                "GET", "/api/v1/stats/referrers", {"days": days, "limit": limit}
            )
            return [ReferrerStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch referrer stats: %s", e)
            return []

    async def get_page_stats(self, days: int = 30, limit: int = 20) -> list[PageStats]:
        """Get statistics by page.

        Args:
            days: Number of days to include.
            limit: Maximum number of pages to return.

        Returns:
            List of PageStats objects.
        """
        try:
            data = await self._request("GET", "/api/v1/stats/pages", {"days": days, "limit": limit})
            return [PageStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch page stats: %s", e)
            return []

    async def get_event_stats(self, days: int = 30, limit: int = 20) -> list[EventStats]:
        """Get statistics by event type.

        Args:
            days: Number of days to include.
            limit: Maximum number of event types to return.

        Returns:
            List of EventStats objects.
        """
        try:
            data = await self._request(
                "GET", "/api/v1/stats/events", {"days": days, "limit": limit}
            )
            return [EventStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch event stats: %s", e)
            return []

    async def get_campaigns(
        self, include_inactive: bool = False, limit: int = 50
    ) -> list[CampaignStats]:
        """Get all campaigns with statistics.

        Args:
            include_inactive: Include inactive campaigns.
            limit: Maximum number of campaigns to return.

        Returns:
            List of CampaignStats objects.
        """
        try:
            data = await self._request(
                "GET",
                "/api/v1/stats/campaigns",
                {"include_inactive": include_inactive, "limit": limit},
            )
            return [CampaignStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch campaigns: %s", e)
            return []

    async def get_campaign_detail(self, campaign_id: UUID, days: int = 30) -> CampaignDetail | None:
        """Get detailed campaign statistics.

        Args:
            campaign_id: The campaign UUID.
            days: Number of days to include in statistics.

        Returns:
            CampaignDetail object or None if not found.
        """
        try:
            data = await self._request(
                "GET", f"/api/v1/stats/campaigns/{campaign_id}", {"days": days}
            )
            return CampaignDetail(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch campaign detail: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch campaign detail: %s", e)
            return None

    async def get_campaign_pixels(
        self, campaign_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[PixelStats]:
        """Get pixels for a campaign.

        Args:
            campaign_id: The campaign UUID.
            limit: Maximum number of pixels to return.
            offset: Number of pixels to skip.

        Returns:
            List of PixelStats objects.
        """
        try:
            data = await self._request(
                "GET",
                f"/api/v1/stats/campaigns/{campaign_id}/pixels",
                {"limit": limit, "offset": offset},
            )
            return [PixelStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch campaign pixels: %s", e)
            return []

    async def get_ip_stats(self, days: int = 30, limit: int = 50) -> list[IPStats]:
        """Get statistics by IP address (most active IPs).

        Args:
            days: Number of days to include.
            limit: Maximum number of IPs to return.

        Returns:
            List of IPStats objects.
        """
        try:
            data = await self._request("GET", "/api/v1/stats/ips", {"days": days, "limit": limit})
            return [IPStats(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch IP stats: %s", e)
            return []

    async def get_ip_detail(self, ip_address: str, days: int = 30) -> IPDetailStats | None:
        """Get detailed statistics for a specific IP address.

        Args:
            ip_address: The IP address to look up.
            days: Number of days to include in statistics.

        Returns:
            IPDetailStats object or None if not found.
        """
        try:
            data = await self._request("GET", f"/api/v1/stats/ips/{ip_address}", {"days": days})
            return IPDetailStats(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch IP detail: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch IP detail: %s", e)
            return None

    # =========================================================================
    # Campaign Management Methods (analytics:write scope)
    # =========================================================================

    async def create_campaign(
        self,
        name: str,
        description: str | None = None,
        destination_url: str | None = None,
        extra_data: dict | None = None,
    ) -> CampaignCreate | None:
        """Create a new analytics campaign for email tracking.

        Args:
            name: Campaign name.
            description: Campaign description.
            destination_url: URL to redirect link clicks to.
            extra_data: Additional metadata.

        Returns:
            CampaignCreate object or None on error.
        """
        try:
            data = await self._request(
                "POST",
                "/api/v1/stats/campaigns",
                json_data={
                    "name": name,
                    "description": description,
                    "destination_url": destination_url,
                    "extra_data": extra_data,
                },
                scope="analytics:write",
            )
            return CampaignCreate(**data)
        except Exception as e:
            logger.exception("Failed to create campaign: %s", e)
            return None

    async def create_pixel(
        self,
        campaign_id: UUID,
        recipient_email: str | None = None,
        recipient_id: str | None = None,
        extra_data: dict | None = None,
    ) -> PixelCreate | None:
        """Create a tracking pixel for an email recipient.

        Args:
            campaign_id: Parent campaign ID.
            recipient_email: Recipient email address.
            recipient_id: Custom recipient identifier.
            extra_data: Additional metadata.

        Returns:
            PixelCreate object or None on error.
        """
        try:
            data = await self._request(
                "POST",
                f"/api/v1/stats/campaigns/{campaign_id}/pixels",
                json_data={
                    "recipient_email": recipient_email,
                    "recipient_id": recipient_id,
                    "extra_data": extra_data,
                },
                scope="analytics:write",
            )
            return PixelCreate(**data)
        except Exception as e:
            logger.exception("Failed to create pixel: %s", e)
            return None

    async def create_pixels_batch(
        self,
        campaign_id: UUID,
        pixels: list[dict],
    ) -> list[PixelCreate]:
        """Create multiple tracking pixels at once.

        Args:
            campaign_id: Parent campaign ID.
            pixels: List of pixel data dicts with recipient_email, recipient_id, extra_data.

        Returns:
            List of created PixelCreate objects.
        """
        try:
            data = await self._request(
                "POST",
                f"/api/v1/stats/campaigns/{campaign_id}/pixels/batch",
                json_data={"pixels": pixels},
                scope="analytics:write",
            )
            return [PixelCreate(**p) for p in data.get("pixels", [])]
        except Exception as e:
            logger.exception("Failed to create pixels batch: %s", e)
            return []

    async def delete_campaign(self, campaign_id: UUID) -> bool:
        """Delete an analytics campaign and all its associated data.

        Args:
            campaign_id: The campaign UUID to delete.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            async with httpx.AsyncClient() as client:
                token = await self._get_access_token(scope="analytics:write")
                response = await client.delete(
                    f"{self._base_url}/api/v1/stats/campaigns/{campaign_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Campaign not found for deletion: %s", campaign_id)
            else:
                logger.exception("Failed to delete campaign: %s", e)
            return False
        except Exception as e:
            logger.exception("Failed to delete campaign: %s", e)
            return False

    async def delete_campaigns_bulk(self, campaign_ids: list[UUID]) -> tuple[int, int]:
        """Delete multiple analytics campaigns.

        Args:
            campaign_ids: List of campaign UUIDs to delete.

        Returns:
            Tuple of (deleted_count, failed_count).
        """
        deleted = 0
        failed = 0

        for campaign_id in campaign_ids:
            success = await self.delete_campaign(campaign_id)
            if success:
                deleted += 1
            else:
                failed += 1

        return deleted, failed

    async def reset_all_analytics(self) -> dict | None:
        """Reset all analytics data. Requires analytics:delete scope (super_admin only).

        WARNING: This permanently deletes ALL analytics data.

        Returns:
            Dict with deletion counts or None on failure.
        """
        try:
            data = await self._request(
                "DELETE",
                "/api/v1/stats/reset",
                scope="analytics:delete",
            )
            return data
        except Exception as e:
            logger.exception("Failed to reset analytics: %s", e)
            return None


# Singleton instance
analytics_client = AnalyticsClient()
