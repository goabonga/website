# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.routes.stats module."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from analytics.routes.stats import (
    BrowserStats,
    CampaignStats,
    CountryStats,
    DailyStats,
    DeviceStats,
    EventStats,
    IPDetailStats,
    IPEventStats,
    IPPageStats,
    IPStats,
    OverviewStats,
    PageStats,
    PixelStats,
    ReferrerStats,
    StatsResponse,
    get_date_range,
)
from httpx import ASGITransport, AsyncClient


class TestGetDateRange:
    """Tests for get_date_range function."""

    def test_returns_tuple(self):
        start, end = get_date_range(30)
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)

    def test_end_is_recent(self):
        _, end = get_date_range(30)
        assert (datetime.now(UTC) - end).total_seconds() < 2

    def test_start_is_days_ago(self):
        start, end = get_date_range(7)
        diff = end - start
        assert abs(diff.days - 7) <= 1


class TestResponseModels:
    """Tests for response model serialization."""

    def test_overview_stats(self):
        now = datetime.now(UTC)
        stats = OverviewStats(
            total_sessions=100,
            unique_visitors=80,
            total_pageviews=500,
            total_events=1000,
            period_start=now - timedelta(days=30),
            period_end=now,
        )
        data = stats.model_dump()
        assert data["total_sessions"] == 100

    def test_daily_stats(self):
        stats = DailyStats(
            date="2025-01-01",
            sessions=10,
            pageviews=50,
            unique_visitors=8,
        )
        assert stats.date == "2025-01-01"

    def test_country_stats(self):
        stats = CountryStats(country="US", sessions=50, percentage=33.33)
        assert stats.country == "US"

    def test_device_stats(self):
        stats = DeviceStats(device_type="desktop", sessions=100, percentage=50.0)
        assert stats.device_type == "desktop"

    def test_browser_stats(self):
        stats = BrowserStats(browser="Chrome", sessions=80, percentage=40.0)
        assert stats.browser == "Chrome"

    def test_referrer_stats(self):
        stats = ReferrerStats(referrer="google.com", sessions=30, percentage=15.0)
        assert stats.referrer == "google.com"

    def test_page_stats(self):
        stats = PageStats(page_url="/home", pageviews=200, unique_sessions=150)
        assert stats.page_url == "/home"

    def test_event_stats(self):
        stats = EventStats(event_type="click", count=300, unique_sessions=200)
        assert stats.event_type == "click"

    def test_ip_stats(self):
        now = datetime.now(UTC)
        stats = IPStats(
            ip_address="1.2.3.4",
            sessions=5,
            pageviews=20,
            countries=["US"],
            browsers=["Chrome"],
            device_types=["desktop"],
            first_seen=now,
            last_seen=now,
        )
        assert stats.ip_address == "1.2.3.4"

    def test_ip_page_stats(self):
        stats = IPPageStats(page_url="/about", pageviews=10)
        assert stats.page_url == "/about"

    def test_ip_event_stats(self):
        stats = IPEventStats(event_type="click", count=5)
        assert stats.event_type == "click"

    def test_ip_detail_stats(self):
        now = datetime.now(UTC)
        stats = IPDetailStats(
            ip_address="1.2.3.4",
            total_sessions=10,
            total_pageviews=50,
            total_events=100,
            countries=["US"],
            cities=["NYC"],
            browsers=["Chrome"],
            device_types=["desktop"],
            operating_systems=["Windows"],
            referrers=["google.com"],
            first_seen=now,
            last_seen=now,
            sessions_by_day=[],
        )
        assert stats.ip_address == "1.2.3.4"

    def test_stats_response(self):
        stats = StatsResponse(success=True, data={"key": "value"})
        assert stats.success is True


class TestCampaignResponseModels:
    """Tests for campaign response models."""

    def test_campaign_stats(self):
        stats = CampaignStats(
            id=uuid.uuid4(),
            name="Test",
            tracking_key="abc",
            is_active=True,
            click_count=10,
            unique_click_count=5,
            pixel_count=3,
            total_opens=20,
            created_at=datetime.now(UTC),
        )
        assert stats.name == "Test"

    def test_pixel_stats(self):
        stats = PixelStats(
            id=uuid.uuid4(),
            pixel_key="pxl123",
            recipient_email="test@example.com",
            recipient_id=None,
            open_count=5,
            first_opened_at=None,
            last_opened_at=None,
            created_at=datetime.now(UTC),
        )
        assert stats.pixel_key == "pxl123"


def _mock_user():
    """Create a fake authenticated user."""
    from analytics.auth.models import User

    return User(
        id=uuid.uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=["analytics:read", "analytics:write", "analytics:delete"],
    )


def _make_scalar_result(value):
    """Create a mock result whose .scalar() returns value."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _make_scalar_one_or_none_result(value):
    """Create a mock result whose .scalar_one_or_none() returns value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_rows_result(rows):
    """Create a mock result whose .all() returns the list of rows."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _make_scalars_result(items):
    """Create a mock result whose .scalars().all() returns items."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


def _make_row(**kwargs):
    """Create a simple namespace-like object for row results."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def patched_app(mock_db):
    """Return the FastAPI app with get_db and auth overridden."""
    from analytics.database import get_db
    from analytics.main import app

    mock_user = _mock_user()

    async def override_get_db():
        yield mock_db

    # Override all auth dependencies used in stats routes.
    # require_scopes returns a dependency function, so we must override
    # each unique dependency. We store the originals and override them.
    # The simplest approach: override get_db, and override all dependencies
    # that are created via require_scopes by replacing the factory.

    app.dependency_overrides[get_db] = override_get_db

    # We need to override every require_scopes dependency.
    # Since require_scopes("analytics:read") creates a new function each time
    # the module is loaded, we must find the actual dependency objects from the routes.
    from analytics.routes.stats import router

    for route in router.routes:
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                # Override any dependency that has a sub-dependency on oauth2_scheme
                dep_callable = dep.call
                if dep_callable is not get_db and dep_callable is not override_get_db:
                    # This is likely an auth dependency
                    async def auth_override():
                        return mock_user

                    app.dependency_overrides[dep_callable] = auth_override

    yield app
    app.dependency_overrides.clear()


class TestGetOverviewStats:
    """Tests for GET /api/v1/stats/overview endpoint."""

    @pytest.mark.asyncio
    async def test_overview_stats(self, patched_app, mock_db):
        # Mock the 4 queries: total_sessions, unique_visitors, pageviews, events
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(100),  # total sessions
                _make_scalar_result(80),  # unique visitors
                _make_scalar_result(500),  # pageviews
                _make_scalar_result(1000),  # events
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/overview?days=30")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 100
        assert data["unique_visitors"] == 80
        assert data["total_pageviews"] == 500
        assert data["total_events"] == 1000

    @pytest.mark.asyncio
    async def test_overview_stats_null_scalars(self, patched_app, mock_db):
        # When no data, scalars return None -> should default to 0
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(None),
                _make_scalar_result(None),
                _make_scalar_result(None),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/overview")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 0
        assert data["unique_visitors"] == 0


class TestGetDailyStats:
    """Tests for GET /api/v1/stats/daily endpoint."""

    @pytest.mark.asyncio
    async def test_daily_stats(self, patched_app, mock_db):
        daily_rows = [
            _make_row(date="2025-01-01", sessions=10, unique_visitors=8),
            _make_row(date="2025-01-02", sessions=15, unique_visitors=12),
        ]
        pageviews_rows = [
            _make_row(date="2025-01-01", pageviews=50),
            _make_row(date="2025-01-02", pageviews=70),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_rows_result(daily_rows),
                _make_rows_result(pageviews_rows),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/daily?days=7")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["date"] == "2025-01-01"
        assert data[0]["sessions"] == 10
        assert data[0]["pageviews"] == 50

    @pytest.mark.asyncio
    async def test_daily_stats_empty(self, patched_app, mock_db):
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_rows_result([]),
                _make_rows_result([]),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/daily")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetCountryStats:
    """Tests for GET /api/v1/stats/countries endpoint."""

    @pytest.mark.asyncio
    async def test_country_stats(self, patched_app, mock_db):
        country_rows = [
            _make_row(country="US", sessions=50),
            _make_row(country="FR", sessions=30),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(100),  # total sessions
                _make_rows_result(country_rows),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/countries")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["country"] == "US"
        assert data[0]["percentage"] == 50.0

    @pytest.mark.asyncio
    async def test_country_stats_zero_total(self, patched_app, mock_db):
        # total_sessions=None -> defaults to 1 to avoid division by zero
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_rows_result([]),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/countries")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetDeviceStats:
    """Tests for GET /api/v1/stats/devices endpoint."""

    @pytest.mark.asyncio
    async def test_device_stats(self, patched_app, mock_db):
        device_rows = [
            _make_row(device_type="desktop", sessions=60),
            _make_row(device_type="mobile", sessions=40),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(100),
                _make_rows_result(device_rows),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/devices")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["device_type"] == "desktop"
        assert data[0]["percentage"] == 60.0


class TestGetBrowserStats:
    """Tests for GET /api/v1/stats/browsers endpoint."""

    @pytest.mark.asyncio
    async def test_browser_stats(self, patched_app, mock_db):
        browser_rows = [
            _make_row(browser="Chrome", sessions=70),
            _make_row(browser="Firefox", sessions=30),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(100),
                _make_rows_result(browser_rows),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/browsers")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["browser"] == "Chrome"
        assert data[0]["percentage"] == 70.0


class TestGetIPStats:
    """Tests for GET /api/v1/stats/ips endpoint."""

    @pytest.mark.asyncio
    async def test_ip_stats(self, patched_app, mock_db):
        now = datetime.now(UTC)
        ip_rows = [
            _make_row(
                ip_address="1.2.3.4",
                sessions=10,
                first_seen=now - timedelta(days=5),
                last_seen=now,
                countries=["US", None],
                browsers=["Chrome", None],
                device_types=["desktop", None],
            ),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_rows_result(ip_rows),
                _make_scalar_result(50),  # pageviews for 1.2.3.4
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/ips")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ip_address"] == "1.2.3.4"
        assert data[0]["sessions"] == 10
        assert data[0]["pageviews"] == 50
        # None values should be filtered out
        assert data[0]["countries"] == ["US"]
        assert data[0]["browsers"] == ["Chrome"]
        assert data[0]["device_types"] == ["desktop"]

    @pytest.mark.asyncio
    async def test_ip_stats_empty(self, patched_app, mock_db):
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_rows_result([]),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/ips")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_ip_stats_null_pageviews(self, patched_app, mock_db):
        now = datetime.now(UTC)
        ip_rows = [
            _make_row(
                ip_address="5.6.7.8",
                sessions=2,
                first_seen=now,
                last_seen=now,
                countries=[],
                browsers=[],
                device_types=[],
            ),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_rows_result(ip_rows),
                _make_scalar_result(None),  # no pageviews
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/ips")

        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["pageviews"] == 0


class TestGetIPDetail:
    """Tests for GET /api/v1/stats/ips/{ip_address} endpoint."""

    @pytest.mark.asyncio
    async def test_ip_detail(self, patched_app, mock_db):
        now = datetime.now(UTC)
        agg_row = _make_row(
            sessions=5,
            first_seen=now - timedelta(days=3),
            last_seen=now,
            countries=["US", None],
            cities=["NYC", None],
            browsers=["Chrome", None],
            device_types=["desktop", None],
            operating_systems=["Windows", None],
            referrers=["google.com", None],
        )
        daily_rows = [
            _make_row(date="2025-01-01", sessions=3),
            _make_row(date="2025-01-02", sessions=2),
        ]
        page_rows = [
            _make_row(page_url="/home", pageviews=10),
        ]
        event_rows = [
            _make_row(event_type="click", count=5),
        ]

        # Mock execute: check, agg, pageviews, events, daily, pages, events_by_type
        agg_result = MagicMock()
        agg_result.one.return_value = agg_row

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(5),  # check IP exists
                agg_result,  # aggregated stats
                _make_scalar_result(20),  # total pageviews
                _make_scalar_result(30),  # total events
                _make_rows_result(daily_rows),  # daily
                _make_rows_result(page_rows),  # pages
                _make_rows_result(event_rows),  # events by type
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/ips/1.2.3.4")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ip_address"] == "1.2.3.4"
        assert data["total_sessions"] == 5
        assert data["total_pageviews"] == 20
        assert data["total_events"] == 30
        assert data["countries"] == ["US"]
        assert data["cities"] == ["NYC"]
        assert len(data["sessions_by_day"]) == 2
        assert len(data["pages"]) == 1
        assert len(data["events"]) == 1

    @pytest.mark.asyncio
    async def test_ip_detail_not_found(self, patched_app, mock_db):
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(0),  # IP not found (0 sessions)
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/ips/9.9.9.9")

        assert resp.status_code == 404


class TestGetReferrerStats:
    """Tests for GET /api/v1/stats/referrers endpoint."""

    @pytest.mark.asyncio
    async def test_referrer_stats(self, patched_app, mock_db):
        referrer_rows = [
            _make_row(referrer="google.com", sessions=40),
            _make_row(referrer="twitter.com", sessions=20),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(60),
                _make_rows_result(referrer_rows),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/referrers")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["referrer"] == "google.com"


class TestGetPageStats:
    """Tests for GET /api/v1/stats/pages endpoint."""

    @pytest.mark.asyncio
    async def test_page_stats(self, patched_app, mock_db):
        page_rows = [
            _make_row(page_url="/home", pageviews=100, unique_sessions=80),
            _make_row(page_url="/about", pageviews=50, unique_sessions=40),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_rows_result(page_rows),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/pages")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["page_url"] == "/home"
        assert data[0]["pageviews"] == 100


class TestGetEventStats:
    """Tests for GET /api/v1/stats/events endpoint."""

    @pytest.mark.asyncio
    async def test_event_stats(self, patched_app, mock_db):
        event_rows = [
            _make_row(event_type="pageview", count=200, unique_sessions=150),
            _make_row(event_type="click", count=80, unique_sessions=60),
        ]
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_rows_result(event_rows),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/events")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["event_type"] == "pageview"


class TestGetCampaigns:
    """Tests for GET /api/v1/stats/campaigns endpoint."""

    @pytest.mark.asyncio
    async def test_get_campaigns(self, patched_app, mock_db):
        now = datetime.now(UTC)
        campaign_id = uuid.uuid4()
        mock_campaign = MagicMock()
        mock_campaign.id = campaign_id
        mock_campaign.name = "Test Campaign"
        mock_campaign.tracking_key = "tk-test"
        mock_campaign.is_active = True
        mock_campaign.click_count = 10
        mock_campaign.unique_click_count = 5
        mock_campaign.created_at = now

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([mock_campaign]),  # campaigns
                _make_scalar_result(3),  # pixel count
                _make_scalar_result(20),  # total opens
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/campaigns")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Campaign"
        assert data[0]["pixel_count"] == 3
        assert data[0]["total_opens"] == 20

    @pytest.mark.asyncio
    async def test_get_campaigns_include_inactive(self, patched_app, mock_db):
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([]),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/campaigns?include_inactive=true")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_campaigns_null_opens(self, patched_app, mock_db):
        now = datetime.now(UTC)
        mock_campaign = MagicMock()
        mock_campaign.id = uuid.uuid4()
        mock_campaign.name = "No Opens"
        mock_campaign.tracking_key = "tk-no"
        mock_campaign.is_active = True
        mock_campaign.click_count = 0
        mock_campaign.unique_click_count = 0
        mock_campaign.created_at = now

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([mock_campaign]),
                _make_scalar_result(None),  # no pixels
                _make_scalar_result(None),  # no opens
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/stats/campaigns")

        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["pixel_count"] == 0
        assert data[0]["total_opens"] == 0


class TestGetCampaignDetail:
    """Tests for GET /api/v1/stats/campaigns/{campaign_id} endpoint."""

    @pytest.mark.asyncio
    async def test_campaign_detail(self, patched_app, mock_db):
        now = datetime.now(UTC)
        campaign_id = uuid.uuid4()
        mock_campaign = MagicMock()
        mock_campaign.id = campaign_id
        mock_campaign.name = "Detail Campaign"
        mock_campaign.description = "A test campaign"
        mock_campaign.tracking_key = "tk-detail"
        mock_campaign.destination_url = "https://example.com"
        mock_campaign.is_active = True
        mock_campaign.click_count = 100
        mock_campaign.unique_click_count = 60
        mock_campaign.created_at = now
        mock_campaign.updated_at = now

        daily_rows = [
            _make_row(date="2025-01-01", sessions=10, unique_visitors=8),
        ]
        country_rows = [
            _make_row(country="US", sessions=50),
        ]

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_one_or_none_result(mock_campaign),  # campaign lookup
                _make_rows_result(daily_rows),  # clicks by day
                _make_scalar_result(50),  # total clicks
                _make_rows_result(country_rows),  # clicks by country
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/stats/campaigns/{campaign_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Detail Campaign"
        assert len(data["clicks_by_day"]) == 1
        assert len(data["clicks_by_country"]) == 1

    @pytest.mark.asyncio
    async def test_campaign_detail_not_found(self, patched_app, mock_db):
        campaign_id = uuid.uuid4()
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_one_or_none_result(None),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/stats/campaigns/{campaign_id}")

        assert resp.status_code == 404


class TestGetCampaignPixels:
    """Tests for GET /api/v1/stats/campaigns/{campaign_id}/pixels endpoint."""

    @pytest.mark.asyncio
    async def test_campaign_pixels(self, patched_app, mock_db):
        now = datetime.now(UTC)
        campaign_id = uuid.uuid4()

        mock_pixel = MagicMock()
        mock_pixel.id = uuid.uuid4()
        mock_pixel.pixel_key = "pxl-1"
        mock_pixel.recipient_email = "user@example.com"
        mock_pixel.recipient_id = None
        mock_pixel.open_count = 3
        mock_pixel.first_opened_at = now
        mock_pixel.last_opened_at = now
        mock_pixel.created_at = now

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_one_or_none_result(campaign_id),  # campaign exists
                _make_scalars_result([mock_pixel]),  # pixels
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/stats/campaigns/{campaign_id}/pixels")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["pixel_key"] == "pxl-1"
        assert data[0]["open_count"] == 3

    @pytest.mark.asyncio
    async def test_campaign_pixels_not_found(self, patched_app, mock_db):
        campaign_id = uuid.uuid4()
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_one_or_none_result(None),
            ]
        )

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/stats/campaigns/{campaign_id}/pixels")

        assert resp.status_code == 404
