# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for synchronous analytics API client."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from internal.services.analytics_client_sync import (
    CampaignCreateResponse,
    CampaignDetailResponse,
    PixelCreateResponse,
    PixelStatsResponse,
    SyncAnalyticsClient,
    get_sync_analytics_client,
)


@pytest.fixture
def client():
    """Create a SyncAnalyticsClient with mocked settings."""
    with patch("internal.services.analytics_client_sync.settings") as s:
        s.analytics_api_url = "https://analytics.example.com"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield SyncAnalyticsClient()


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
    def test_fetches_new_token(self, client):
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.analytics_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("analytics:write")
            assert token == "new-token"

    def test_returns_cached_token(self, client):
        client._tokens["analytics:write"] = (
            "cached-token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        token = client._get_access_token("analytics:write")
        assert token == "cached-token"

    def test_refreshes_expired_token(self, client):
        client._tokens["analytics:write"] = (
            "expired-token",
            datetime.now(UTC) - timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("fresh-token")

        with patch("internal.services.analytics_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("analytics:write")
            assert token == "fresh-token"

    def test_refreshes_near_expiry_token(self, client):
        client._tokens["analytics:write"] = (
            "near-expiry-token",
            datetime.now(UTC) + timedelta(seconds=10),
        )
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.analytics_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("analytics:write")
            assert token == "new-token"

    def test_raises_when_no_issuer(self):
        with patch("internal.services.analytics_client_sync.settings") as s:
            s.analytics_api_url = "https://analytics.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = ""
            c = SyncAnalyticsClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                c._get_access_token()

    def test_caches_token_per_scope(self, client):
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("write-token")

        with patch("internal.services.analytics_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("analytics:write")
            assert token == "write-token"
            assert "analytics:write" in client._tokens

    def test_default_expires_in(self, client):
        mock_http = MagicMock()
        mock_http.post.return_value = httpx.Response(
            200,
            json={"access_token": "tok"},
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        with patch("internal.services.analytics_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("analytics:write")
            assert token == "tok"
            assert "analytics:write" in client._tokens


# =========================================================================
# _request
# =========================================================================


class TestRequest:
    def test_returns_empty_when_not_configured(self):
        with patch("internal.services.analytics_client_sync.settings") as s:
            s.analytics_api_url = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = SyncAnalyticsClient()
            result = c._request("GET", "/test")
            assert result == {}

    def test_success(self, client):
        client._tokens["analytics:write"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = _json_response({"items": [1, 2]})

        with patch("internal.services.analytics_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = client._request("GET", "/api/v1/test")
            assert result == {"items": [1, 2]}

    def test_propagates_token_error(self, client):
        with (
            patch.object(client, "_get_access_token", side_effect=Exception("token fail")),
            pytest.raises(Exception, match="token fail"),
        ):
            client._request("GET", "/test")

    def test_request_with_params_and_json(self, client):
        client._tokens["analytics:write"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = _json_response({"ok": True})

        with patch("internal.services.analytics_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = client._request(
                "POST",
                "/api/v1/test",
                params={"key": "val"},
                json_data={"name": "test"},
                scope="analytics:write",
            )
            assert result == {"ok": True}
            mock_http.request.assert_called_once()


# =========================================================================
# create_campaign
# =========================================================================


class TestCreateCampaign:
    def test_success(self, client):
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
        with patch.object(client, "_request", return_value=data) as mock_req:
            result = client.create_campaign(
                name="New Campaign",
                description="A description",
                destination_url="https://example.com",
                extra_data={"key": "val"},
            )
            assert isinstance(result, CampaignCreateResponse)
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
            )

    def test_empty_data_returns_none(self, client):
        with patch.object(client, "_request", return_value={}):
            result = client.create_campaign(name="Test")
            assert result is None

    def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = client.create_campaign(name="Test")
            assert result is None


# =========================================================================
# create_pixel
# =========================================================================


class TestCreatePixel:
    def test_success(self, client):
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
        with patch.object(client, "_request", return_value=data):
            result = client.create_pixel(
                campaign_id=cid,
                recipient_email="test@example.com",
            )
            assert isinstance(result, PixelCreateResponse)
            assert result.pixel_key == "px1"

    def test_empty_data_returns_none(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", return_value={}):
            result = client.create_pixel(campaign_id=cid)
            assert result is None

    def test_error_returns_none(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = client.create_pixel(campaign_id=cid)
            assert result is None


# =========================================================================
# create_pixels_batch
# =========================================================================


class TestCreatePixelsBatch:
    def test_success(self, client):
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
        with patch.object(client, "_request", return_value=data):
            result = client.create_pixels_batch(
                campaign_id=cid,
                pixels=[
                    {"recipient_email": "a@example.com"},
                    {"recipient_email": "b@example.com"},
                ],
            )
            assert len(result) == 2
            assert isinstance(result[0], PixelCreateResponse)

    def test_empty_data_returns_empty(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", return_value={}):
            result = client.create_pixels_batch(campaign_id=cid, pixels=[])
            assert result == []

    def test_empty_pixels_key(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", return_value={"pixels": []}):
            result = client.create_pixels_batch(campaign_id=cid, pixels=[])
            assert result == []

    def test_error_returns_empty(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = client.create_pixels_batch(campaign_id=cid, pixels=[])
            assert result == []


# =========================================================================
# get_campaign_detail
# =========================================================================


class TestGetCampaignDetail:
    def test_success(self, client):
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
        }
        with patch.object(client, "_request", return_value=data) as mock_req:
            result = client.get_campaign_detail(cid, days=7)
            assert isinstance(result, CampaignDetailResponse)
            assert result.name == "Campaign 1"
            mock_req.assert_called_once_with(
                "GET",
                f"/api/v1/stats/campaigns/{cid}",
                params={"days": 7},
                scope="analytics:read",
            )

    def test_empty_data_returns_none(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", return_value={}):
            result = client.get_campaign_detail(cid)
            assert result is None

    def test_error_returns_none(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = client.get_campaign_detail(cid)
            assert result is None


# =========================================================================
# get_campaign_pixels
# =========================================================================


class TestGetCampaignPixels:
    def test_success(self, client):
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
        with patch.object(client, "_request", return_value=data) as mock_req:
            result = client.get_campaign_pixels(cid, limit=50, offset=10)
            assert len(result) == 1
            assert isinstance(result[0], PixelStatsResponse)
            assert result[0].pixel_key == "px1"
            mock_req.assert_called_once_with(
                "GET",
                f"/api/v1/stats/campaigns/{cid}/pixels",
                params={"limit": 50, "offset": 10},
                scope="analytics:read",
            )

    def test_empty_data_returns_empty(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", return_value={}):
            result = client.get_campaign_pixels(cid)
            assert result == []

    def test_error_returns_empty(self, client):
        cid = uuid.uuid4()
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = client.get_campaign_pixels(cid)
            assert result == []


# =========================================================================
# get_sync_analytics_client factory
# =========================================================================


class TestGetSyncAnalyticsClient:
    def test_returns_instance(self):
        with patch("internal.services.analytics_client_sync.settings") as s:
            s.analytics_api_url = "https://analytics.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            result = get_sync_analytics_client()
            assert isinstance(result, SyncAnalyticsClient)


# =========================================================================
# Pydantic Models
# =========================================================================


class TestPydanticModels:
    def test_campaign_create_response(self):
        cid = uuid.uuid4()
        resp = CampaignCreateResponse(
            id=cid,
            name="Test",
            description=None,
            tracking_key="key1",
            destination_url=None,
            is_active=True,
            created_at=datetime(2024, 1, 1),
        )
        assert resp.name == "Test"
        assert resp.description is None

    def test_pixel_create_response(self):
        pid = uuid.uuid4()
        cid = uuid.uuid4()
        resp = PixelCreateResponse(
            id=pid,
            pixel_key="px1",
            campaign_id=cid,
            recipient_email="test@test.com",
            recipient_id=None,
            created_at=datetime(2024, 1, 1),
        )
        assert resp.pixel_key == "px1"

    def test_campaign_detail_response(self):
        cid = uuid.uuid4()
        resp = CampaignDetailResponse(
            id=cid,
            name="Test",
            description=None,
            tracking_key="key1",
            destination_url=None,
            is_active=True,
            click_count=10,
            unique_click_count=5,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 2),
        )
        assert resp.click_count == 10

    def test_pixel_stats_response(self):
        pid = uuid.uuid4()
        resp = PixelStatsResponse(
            id=pid,
            pixel_key="px1",
            recipient_email=None,
            recipient_id=None,
            open_count=0,
            first_opened_at=None,
            last_opened_at=None,
            created_at=datetime(2024, 1, 1),
        )
        assert resp.open_count == 0
        assert resp.first_opened_at is None
