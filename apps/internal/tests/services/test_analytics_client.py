# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics API client."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from internal.services.analytics_client import (
    AnalyticsClient,
    BrowserStats,
    CampaignCreate,
    CampaignDetail,
    CampaignStats,
    CountryStats,
    DailyStats,
    DeviceStats,
    EventStats,
    IPDetailStats,
    IPStats,
    OverviewStats,
    PageStats,
    PixelCreate,
    PixelStats,
    ReferrerStats,
)


@pytest.fixture
def client():
    """Create an AnalyticsClient with mocked settings."""
    with patch("internal.services.analytics_client.settings") as s:
        s.analytics_api_url = "https://analytics.example.com"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield AnalyticsClient()


def _token_response(token="test-token", expires_in=3600):
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": expires_in},
        request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
    )


def _json_response(data, status_code=200):
    return httpx.Response(
        status_code,
        json=data,
        request=httpx.Request("GET", "https://analytics.example.com/api/v1/test"),
    )


# =========================================================================
# _get_access_token
# =========================================================================


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_fetches_new_token(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("analytics:read")
            assert token == "new-token"

    @pytest.mark.asyncio
    async def test_returns_cached_token(self, client):
        client._tokens["analytics:read"] = (
            "cached-token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        token = await client._get_access_token("analytics:read")
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_refreshes_expired_token(self, client):
        client._tokens["analytics:read"] = (
            "expired-token",
            datetime.now(UTC) - timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("fresh-token")

        with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("analytics:read")
            assert token == "fresh-token"

    @pytest.mark.asyncio
    async def test_refreshes_near_expiry_token(self, client):
        # Token within 30 seconds of expiry should be refreshed
        client._tokens["analytics:read"] = (
            "near-expiry-token",
            datetime.now(UTC) + timedelta(seconds=10),
        )
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("analytics:read")
            assert token == "new-token"

    @pytest.mark.asyncio
    async def test_raises_when_no_issuer(self):
        with patch("internal.services.analytics_client.settings") as s:
            s.analytics_api_url = "https://analytics.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = ""
            c = AnalyticsClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                await c._get_access_token()

    @pytest.mark.asyncio
    async def test_caches_token_per_scope(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("write-token")

        with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("analytics:write")
            assert token == "write-token"
            assert "analytics:write" in client._tokens

    @pytest.mark.asyncio
    async def test_default_expires_in(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = httpx.Response(
            200,
            json={"access_token": "tok"},
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("analytics:read")
            assert token == "tok"
            assert "analytics:read" in client._tokens


# =========================================================================
# _request
# =========================================================================


class TestRequest:
    @pytest.mark.asyncio
    async def test_raises_when_no_base_url(self):
        with patch("internal.services.analytics_client.settings") as s:
            s.analytics_api_url = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = AnalyticsClient()
            with pytest.raises(ValueError, match="analytics_api_url not configured"):
                await c._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_success(self, client):
        client._tokens["analytics:read"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = _json_response({"items": [1, 2]})

        with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("GET", "/api/v1/test")
            assert result == {"items": [1, 2]}

    @pytest.mark.asyncio
    async def test_propagates_token_error(self, client):
        with (
            patch.object(client, "_get_access_token", side_effect=Exception("token fail")),
            pytest.raises(Exception, match="token fail"),
        ):
            await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_request_with_params_and_json(self, client):
        client._tokens["analytics:write"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = _json_response({"ok": True})

        with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request(
                "POST",
                "/api/v1/test",
                params={"key": "val"},
                json_data={"name": "test"},
                scope="analytics:write",
            )
            assert result == {"ok": True}
            mock_http.request.assert_called_once()
            call_kwargs = mock_http.request.call_args
            assert call_kwargs[1]["params"] == {"key": "val"}
            assert call_kwargs[1]["json"] == {"name": "test"}


# =========================================================================
# get_overview
# =========================================================================


class TestGetOverview:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = {
            "total_sessions": 100,
            "unique_visitors": 50,
            "total_pageviews": 200,
            "total_events": 30,
            "period_start": "2024-01-01T00:00:00",
            "period_end": "2024-01-31T23:59:59",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_overview(days=30)
            assert isinstance(result, OverviewStats)
            assert result.total_sessions == 100
            assert result.unique_visitors == 50

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_overview()
            assert result is None


# =========================================================================
# get_daily_stats
# =========================================================================


class TestGetDailyStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {"date": "2024-01-01", "sessions": 10, "pageviews": 20, "unique_visitors": 5},
            {"date": "2024-01-02", "sessions": 15, "pageviews": 30, "unique_visitors": 8},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_daily_stats(days=7)
            assert len(result) == 2
            assert isinstance(result[0], DailyStats)
            assert result[0].date == "2024-01-01"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_daily_stats()
            assert result == []


# =========================================================================
# get_country_stats
# =========================================================================


class TestGetCountryStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {"country": "US", "sessions": 50, "percentage": 50.0},
            {"country": "FR", "sessions": 30, "percentage": 30.0},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_country_stats(days=30, limit=10)
            assert len(result) == 2
            assert isinstance(result[0], CountryStats)
            assert result[0].country == "US"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_country_stats()
            assert result == []


# =========================================================================
# get_device_stats
# =========================================================================


class TestGetDeviceStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {"device_type": "desktop", "sessions": 60, "percentage": 60.0},
            {"device_type": "mobile", "sessions": 40, "percentage": 40.0},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_device_stats(days=30)
            assert len(result) == 2
            assert isinstance(result[0], DeviceStats)
            assert result[0].device_type == "desktop"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_device_stats()
            assert result == []


# =========================================================================
# get_browser_stats
# =========================================================================


class TestGetBrowserStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {"browser": "Chrome", "sessions": 70, "percentage": 70.0},
            {"browser": "Firefox", "sessions": 20, "percentage": 20.0},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_browser_stats(days=30, limit=10)
            assert len(result) == 2
            assert isinstance(result[0], BrowserStats)
            assert result[0].browser == "Chrome"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_browser_stats()
            assert result == []


# =========================================================================
# get_referrer_stats
# =========================================================================


class TestGetReferrerStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {"referrer": "google.com", "sessions": 40, "percentage": 40.0},
            {"referrer": None, "sessions": 30, "percentage": 30.0},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_referrer_stats(days=30, limit=10)
            assert len(result) == 2
            assert isinstance(result[0], ReferrerStats)
            assert result[0].referrer == "google.com"
            assert result[1].referrer is None

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_referrer_stats()
            assert result == []


# =========================================================================
# get_page_stats
# =========================================================================


class TestGetPageStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {"page_url": "/home", "pageviews": 100, "unique_sessions": 50},
            {"page_url": "/about", "pageviews": 40, "unique_sessions": 30},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_page_stats(days=30, limit=20)
            assert len(result) == 2
            assert isinstance(result[0], PageStats)
            assert result[0].page_url == "/home"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_page_stats()
            assert result == []


# =========================================================================
# get_event_stats
# =========================================================================


class TestGetEventStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {"event_type": "click", "count": 200, "unique_sessions": 100},
            {"event_type": "signup", "count": 50, "unique_sessions": 50},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_event_stats(days=30, limit=20)
            assert len(result) == 2
            assert isinstance(result[0], EventStats)
            assert result[0].event_type == "click"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_event_stats()
            assert result == []


# =========================================================================
# get_campaigns
# =========================================================================


class TestGetCampaigns:
    @pytest.mark.asyncio
    async def test_success(self, client):
        cid = str(uuid.uuid4())
        data = [
            {
                "id": cid,
                "name": "Campaign 1",
                "tracking_key": "key1",
                "is_active": True,
                "click_count": 100,
                "unique_click_count": 80,
                "pixel_count": 5,
                "total_opens": 200,
                "created_at": "2024-01-01T00:00:00",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_campaigns(include_inactive=True, limit=50)
            assert len(result) == 1
            assert isinstance(result[0], CampaignStats)
            assert result[0].name == "Campaign 1"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_campaigns()
            assert result == []


# =========================================================================
# get_campaign_detail
# =========================================================================


class TestGetCampaignDetail:
    @pytest.mark.asyncio
    async def test_success(self, client):
        cid = uuid.uuid4()
        data = {
            "id": str(cid),
            "name": "Campaign 1",
            "description": "A campaign",
            "tracking_key": "key1",
            "destination_url": "https://example.com",
            "is_active": True,
            "click_count": 100,
            "unique_click_count": 80,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-02T00:00:00",
            "clicks_by_day": [],
            "clicks_by_country": [],
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_campaign_detail(cid, days=30)
            assert isinstance(result, CampaignDetail)
            assert result.name == "Campaign 1"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, client):
        cid = uuid.uuid4()
        error_response = httpx.Response(
            404,
            request=httpx.Request(
                "GET", f"https://analytics.example.com/api/v1/stats/campaigns/{cid}"
            ),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "404", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_campaign_detail(cid)
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_404_returns_none(self, client):
        cid = uuid.uuid4()
        error_response = httpx.Response(
            500,
            request=httpx.Request(
                "GET", f"https://analytics.example.com/api/v1/stats/campaigns/{cid}"
            ),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_campaign_detail(cid)
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error_returns_none(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_campaign_detail(cid)
            assert result is None


# =========================================================================
# get_campaign_pixels
# =========================================================================


class TestGetCampaignPixels:
    @pytest.mark.asyncio
    async def test_success(self, client):
        cid = uuid.uuid4()
        pid = str(uuid.uuid4())
        data = [
            {
                "id": pid,
                "pixel_key": "px1",
                "recipient_email": "test@example.com",
                "recipient_id": None,
                "open_count": 3,
                "first_opened_at": "2024-01-15T10:00:00",
                "last_opened_at": "2024-01-20T10:00:00",
                "created_at": "2024-01-01T00:00:00",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_campaign_pixels(cid, limit=100, offset=0)
            assert len(result) == 1
            assert isinstance(result[0], PixelStats)
            assert result[0].pixel_key == "px1"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_campaign_pixels(cid)
            assert result == []


# =========================================================================
# get_ip_stats
# =========================================================================


class TestGetIPStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = [
            {
                "ip_address": "1.2.3.4",
                "sessions": 10,
                "pageviews": 50,
                "countries": ["US"],
                "browsers": ["Chrome"],
                "device_types": ["desktop"],
                "first_seen": "2024-01-01T00:00:00",
                "last_seen": "2024-01-31T00:00:00",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_ip_stats(days=30, limit=50)
            assert len(result) == 1
            assert isinstance(result[0], IPStats)
            assert result[0].ip_address == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_ip_stats()
            assert result == []


# =========================================================================
# get_ip_detail
# =========================================================================


class TestGetIPDetail:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = {
            "ip_address": "1.2.3.4",
            "total_sessions": 10,
            "total_pageviews": 50,
            "total_events": 5,
            "countries": ["US"],
            "cities": ["New York"],
            "browsers": ["Chrome"],
            "device_types": ["desktop"],
            "operating_systems": ["Windows"],
            "referrers": ["google.com"],
            "first_seen": "2024-01-01T00:00:00",
            "last_seen": "2024-01-31T00:00:00",
            "sessions_by_day": [],
            "pages": [],
            "events": [],
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.get_ip_detail("1.2.3.4", days=30)
            assert isinstance(result, IPDetailStats)
            assert result.ip_address == "1.2.3.4"
            assert result.total_sessions == 10

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, client):
        error_response = httpx.Response(
            404,
            request=httpx.Request("GET", "https://analytics.example.com/api/v1/stats/ips/1.2.3.4"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "404", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_ip_detail("1.2.3.4")
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_404_returns_none(self, client):
        error_response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://analytics.example.com/api/v1/stats/ips/1.2.3.4"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_ip_detail("1.2.3.4")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_ip_detail("1.2.3.4")
            assert result is None


# =========================================================================
# create_campaign
# =========================================================================


class TestCreateCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        cid = str(uuid.uuid4())
        data = {
            "id": cid,
            "name": "New Campaign",
            "description": "A description",
            "tracking_key": "key1",
            "destination_url": "https://example.com",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=data
        ) as mock_req:
            result = await client.create_campaign(
                name="New Campaign",
                description="A description",
                destination_url="https://example.com",
                extra_data={"key": "val"},
            )
            assert isinstance(result, CampaignCreate)
            assert result.name == "New Campaign"
            mock_req.assert_called_once_with(
                "POST",
                "/api/v1/stats/campaigns",
                json_data={
                    "name": "New Campaign",
                    "description": "A description",
                    "destination_url": "https://example.com",
                    "extra_data": {"key": "val"},
                },
                scope="analytics:write",
            )

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_campaign(name="Test")
            assert result is None


# =========================================================================
# create_pixel
# =========================================================================


class TestCreatePixel:
    @pytest.mark.asyncio
    async def test_success(self, client):
        cid = uuid.uuid4()
        pid = str(uuid.uuid4())
        data = {
            "id": pid,
            "pixel_key": "px1",
            "campaign_id": str(cid),
            "recipient_email": "test@example.com",
            "recipient_id": None,
            "created_at": "2024-01-01T00:00:00",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.create_pixel(
                campaign_id=cid,
                recipient_email="test@example.com",
            )
            assert isinstance(result, PixelCreate)
            assert result.pixel_key == "px1"

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_pixel(campaign_id=cid)
            assert result is None


# =========================================================================
# create_pixels_batch
# =========================================================================


class TestCreatePixelsBatch:
    @pytest.mark.asyncio
    async def test_success(self, client):
        cid = uuid.uuid4()
        pid1 = str(uuid.uuid4())
        pid2 = str(uuid.uuid4())
        data = {
            "pixels": [
                {
                    "id": pid1,
                    "pixel_key": "px1",
                    "campaign_id": str(cid),
                    "recipient_email": "a@example.com",
                    "recipient_id": None,
                    "created_at": "2024-01-01T00:00:00",
                },
                {
                    "id": pid2,
                    "pixel_key": "px2",
                    "campaign_id": str(cid),
                    "recipient_email": "b@example.com",
                    "recipient_id": None,
                    "created_at": "2024-01-01T00:00:00",
                },
            ]
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.create_pixels_batch(
                campaign_id=cid,
                pixels=[
                    {"recipient_email": "a@example.com"},
                    {"recipient_email": "b@example.com"},
                ],
            )
            assert len(result) == 2
            assert isinstance(result[0], PixelCreate)

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_pixels_batch(campaign_id=cid, pixels=[])
            assert result == []

    @pytest.mark.asyncio
    async def test_empty_pixels_key(self, client):
        cid = uuid.uuid4()
        data = {"pixels": []}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.create_pixels_batch(campaign_id=cid, pixels=[])
            assert result == []

    @pytest.mark.asyncio
    async def test_missing_pixels_key(self, client):
        cid = uuid.uuid4()
        data = {}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=data):
            result = await client.create_pixels_batch(campaign_id=cid, pixels=[])
            assert result == []


# =========================================================================
# delete_campaign
# =========================================================================


class TestDeleteCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        cid = uuid.uuid4()
        with patch.object(
            client, "_get_access_token", new_callable=AsyncMock, return_value="token"
        ):
            mock_http = AsyncMock()
            mock_http.delete.return_value = httpx.Response(
                204,
                request=httpx.Request(
                    "DELETE", f"https://analytics.example.com/api/v1/stats/campaigns/{cid}"
                ),
            )

            with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await client.delete_campaign(cid)
                assert result is True

    @pytest.mark.asyncio
    async def test_not_found_returns_false(self, client):
        cid = uuid.uuid4()
        with patch.object(
            client, "_get_access_token", new_callable=AsyncMock, return_value="token"
        ):
            mock_http = AsyncMock()
            error_response = httpx.Response(
                404,
                request=httpx.Request(
                    "DELETE", f"https://analytics.example.com/api/v1/stats/campaigns/{cid}"
                ),
            )
            mock_http.delete.return_value = error_response

            with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                # raise_for_status will raise HTTPStatusError for 404
                mock_http.delete.return_value.raise_for_status = lambda: (_ for _ in ()).throw(
                    httpx.HTTPStatusError(
                        "404", request=error_response.request, response=error_response
                    )
                )

                result = await client.delete_campaign(cid)
                assert result is False

    @pytest.mark.asyncio
    async def test_http_error_non_404_returns_false(self, client):
        cid = uuid.uuid4()
        with patch.object(
            client, "_get_access_token", new_callable=AsyncMock, return_value="token"
        ):
            mock_http = AsyncMock()
            error_response = httpx.Response(
                500,
                request=httpx.Request(
                    "DELETE", f"https://analytics.example.com/api/v1/stats/campaigns/{cid}"
                ),
            )
            mock_http.delete.return_value = error_response
            mock_http.delete.return_value.raise_for_status = lambda: (_ for _ in ()).throw(
                httpx.HTTPStatusError(
                    "500", request=error_response.request, response=error_response
                )
            )

            with patch("internal.services.analytics_client.httpx.AsyncClient") as MockClient:
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await client.delete_campaign(cid)
                assert result is False

    @pytest.mark.asyncio
    async def test_generic_error_returns_false(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_get_access_token", side_effect=Exception("fail")):
            result = await client.delete_campaign(cid)
            assert result is False


# =========================================================================
# delete_campaigns_bulk
# =========================================================================


class TestDeleteCampaignsBulk:
    @pytest.mark.asyncio
    async def test_all_succeed(self, client):
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        with patch.object(client, "delete_campaign", new_callable=AsyncMock, return_value=True):
            deleted, failed = await client.delete_campaigns_bulk(ids)
            assert deleted == 3
            assert failed == 0

    @pytest.mark.asyncio
    async def test_mixed_results(self, client):
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        with patch.object(
            client,
            "delete_campaign",
            new_callable=AsyncMock,
            side_effect=[True, False, True],
        ):
            deleted, failed = await client.delete_campaigns_bulk(ids)
            assert deleted == 2
            assert failed == 1

    @pytest.mark.asyncio
    async def test_all_fail(self, client):
        ids = [uuid.uuid4(), uuid.uuid4()]
        with patch.object(client, "delete_campaign", new_callable=AsyncMock, return_value=False):
            deleted, failed = await client.delete_campaigns_bulk(ids)
            assert deleted == 0
            assert failed == 2

    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        deleted, failed = await client.delete_campaigns_bulk([])
        assert deleted == 0
        assert failed == 0


# =========================================================================
# reset_all_analytics
# =========================================================================


class TestResetAllAnalytics:
    @pytest.mark.asyncio
    async def test_success(self, client):
        data = {"sessions_deleted": 100, "pageviews_deleted": 200}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=data
        ) as mock_req:
            result = await client.reset_all_analytics()
            assert result == data
            mock_req.assert_called_once_with(
                "DELETE",
                "/api/v1/stats/reset",
                scope="analytics:delete",
            )

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.reset_all_analytics()
            assert result is None


# =========================================================================
# Pydantic Models
# =========================================================================


class TestPydanticModels:
    def test_overview_stats(self):
        stats = OverviewStats(
            total_sessions=100,
            unique_visitors=50,
            total_pageviews=200,
            total_events=30,
            period_start=datetime(2024, 1, 1),
            period_end=datetime(2024, 1, 31),
        )
        assert stats.total_sessions == 100

    def test_daily_stats(self):
        stats = DailyStats(date="2024-01-01", sessions=10, pageviews=20, unique_visitors=5)
        assert stats.date == "2024-01-01"

    def test_ip_detail_stats_defaults(self):
        stats = IPDetailStats(
            ip_address="1.2.3.4",
            total_sessions=1,
            total_pageviews=2,
            total_events=0,
            countries=["US"],
            cities=["NYC"],
            browsers=["Chrome"],
            device_types=["desktop"],
            operating_systems=["Win"],
            referrers=[],
            first_seen=datetime(2024, 1, 1),
            last_seen=datetime(2024, 1, 31),
            sessions_by_day=[],
        )
        assert stats.pages == []
        assert stats.events == []
