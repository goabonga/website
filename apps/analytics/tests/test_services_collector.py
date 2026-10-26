# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.services.collector module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from analytics.services.collector import CollectorService, generate_tracking_key, get_client_ip
from analytics.services.geoip import GeoLocation
from analytics.services.useragent import DeviceInfo


class TestGenerateTrackingKey:
    """Tests for generate_tracking_key function."""

    def test_returns_string(self):
        key = generate_tracking_key()
        assert isinstance(key, str)

    def test_default_length_produces_output(self):
        key = generate_tracking_key()
        assert len(key) > 0

    def test_keys_are_unique(self):
        keys = {generate_tracking_key() for _ in range(100)}
        assert len(keys) == 100

    def test_custom_length(self):
        short_key = generate_tracking_key(8)
        long_key = generate_tracking_key(32)
        assert len(short_key) < len(long_key)


class TestGetClientIp:
    """Tests for get_client_ip function."""

    def _make_request(self, headers=None, client_host="127.0.0.1"):
        request = MagicMock()
        request.headers = headers or {}
        if client_host:
            request.client = MagicMock()
            request.client.host = client_host
        else:
            request.client = None
        return request

    def test_from_client_host(self):
        request = self._make_request(client_host="10.0.0.1")
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = False
            result = get_client_ip(request)
        assert result == "10.0.0.1"

    def test_from_x_forwarded_for(self):
        request = self._make_request(
            headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"},
            client_host="10.0.0.1",
        )
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = False
            result = get_client_ip(request)
        assert result == "1.2.3.4"

    def test_no_client_returns_unknown(self):
        request = self._make_request(client_host=None)
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = False
            result = get_client_ip(request)
        assert result == "unknown"

    def test_anonymize_ipv4(self):
        request = self._make_request(client_host="192.168.1.100")
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = True
            result = get_client_ip(request)
        assert result == "192.168.1.0"

    def test_anonymize_ipv6(self):
        request = self._make_request(client_host="2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = True
            result = get_client_ip(request)
        assert result == "2001:0db8:85a3::"

    def test_anonymize_ipv6_short_not_masked(self):
        """IPv6-like string with fewer than 3 colon-segments is returned as-is."""
        request = self._make_request(client_host="fe80:1")
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = True
            result = get_client_ip(request)
        assert result == "fe80:1"

    def test_anonymize_ipv4_malformed_not_masked(self):
        """IPv4-like string with != 4 octets is returned as-is."""
        request = self._make_request(client_host="10.0.1")
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = True
            result = get_client_ip(request)
        assert result == "10.0.1"

    def test_anonymize_unknown_skipped(self):
        request = self._make_request(client_host=None)
        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = True
            result = get_client_ip(request)
        assert result == "unknown"


def _make_mock_request(
    client_host="1.2.3.4",
    user_agent="TestAgent/1.0",
    referer="https://example.com/ref",
    utm_source="test_source",
    utm_medium="test_medium",
    utm_campaign="test_campaign",
    utm_term="test_term",
    utm_content="test_content",
    url="https://example.com/page",
):
    """Build a mock FastAPI Request suitable for CollectorService methods."""
    request = MagicMock()
    headers = {"user-agent": user_agent}
    if referer is not None:
        headers["referer"] = referer
    request.headers = headers
    if client_host:
        request.client = MagicMock()
        request.client.host = client_host
    else:
        request.client = None
    request.query_params = {
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_term": utm_term,
        "utm_content": utm_content,
    }
    request.url = url
    return request


def _mock_async_session():
    """Build a mock AsyncSession with synchronous methods properly mocked."""
    db = AsyncMock()
    db.add = MagicMock()  # add() is synchronous in SQLAlchemy
    db.delete = MagicMock()
    return db


def _make_mock_db():
    """Build a mock AsyncSession with execute returning a MagicMock result."""
    mock_db = _mock_async_session()
    mock_result = MagicMock()
    mock_db.execute.return_value = mock_result
    return mock_db, mock_result


def _default_geo():
    return GeoLocation(country="US", city="New York")


def _default_device_info():
    return DeviceInfo(
        device_type="desktop",
        browser="Chrome",
        browser_version="120.0",
        os="Linux",
        os_version="6.1",
        is_bot=False,
    )


@pytest.mark.asyncio
class TestCollectorServiceGetOrCreateSession:
    """Tests for CollectorService.get_or_create_session."""

    async def test_existing_session_found(self):
        """When a valid session_id is provided and found in the DB, return it
        with is_new=False and update last_seen."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()

        existing_session = MagicMock()
        existing_session.user_id = None
        existing_session.last_seen = datetime(2025, 1, 1)
        mock_result.scalar_one_or_none.return_value = existing_session

        request = _make_mock_request()

        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = False
            session, is_new = await service.get_or_create_session(
                db=mock_db,
                request=request,
                session_id="existing-session-id",
            )

        assert session is existing_session
        assert is_new is False
        # last_seen should have been updated
        assert session.last_seen != datetime(2025, 1, 1)
        mock_db.commit.assert_awaited_once()

    async def test_existing_session_links_user_id(self):
        """When an existing session has no user_id but one is provided,
        link the user_id to the session."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()

        existing_session = MagicMock()
        existing_session.user_id = None
        mock_result.scalar_one_or_none.return_value = existing_session

        user_id = uuid.uuid4()
        request = _make_mock_request()

        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = False
            session, is_new = await service.get_or_create_session(
                db=mock_db,
                request=request,
                session_id="existing-session-id",
                user_id=user_id,
            )

        assert session.user_id == user_id
        assert is_new is False

    async def test_existing_session_does_not_overwrite_user_id(self):
        """If the existing session already has a user_id, it should NOT be
        overwritten even if a different user_id is provided."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()

        original_user_id = uuid.uuid4()
        existing_session = MagicMock()
        existing_session.user_id = original_user_id
        mock_result.scalar_one_or_none.return_value = existing_session

        new_user_id = uuid.uuid4()
        request = _make_mock_request()

        with patch("analytics.services.collector.settings") as mock_settings:
            mock_settings.anonymize_ip = False
            session, is_new = await service.get_or_create_session(
                db=mock_db,
                request=request,
                session_id="existing-session-id",
                user_id=new_user_id,
            )

        # user_id should remain the original
        assert session.user_id == original_user_id
        assert is_new is False

    @patch("analytics.services.collector.useragent_service")
    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_create_new_session_no_session_id(
        self, mock_settings, mock_geoip, mock_useragent
    ):
        """When no session_id is provided, create a brand-new session."""
        service = CollectorService()
        mock_db = _mock_async_session()
        mock_settings.anonymize_ip = False

        mock_geoip.lookup.return_value = _default_geo()
        mock_useragent.parse.return_value = _default_device_info()

        request = _make_mock_request()

        session, is_new = await service.get_or_create_session(
            db=mock_db,
            request=request,
            session_id=None,
        )

        assert is_new is True
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

        # Verify the Session object was constructed correctly
        created_session = mock_db.add.call_args[0][0]
        assert created_session.session_id is not None
        assert len(created_session.session_id) > 0
        assert created_session.ip_address == "1.2.3.4"
        assert created_session.country == "US"
        assert created_session.city == "New York"
        assert created_session.user_agent == "TestAgent/1.0"
        assert created_session.device_type == "desktop"
        assert created_session.browser == "Chrome"
        assert created_session.browser_version == "120.0"
        assert created_session.os == "Linux"
        assert created_session.os_version == "6.1"
        assert created_session.referrer == "https://example.com/ref"
        assert created_session.utm_source == "test_source"
        assert created_session.utm_medium == "test_medium"
        assert created_session.utm_campaign == "test_campaign"
        assert created_session.utm_term == "test_term"
        assert created_session.utm_content == "test_content"
        assert created_session.landing_page == "https://example.com/page"

    @patch("analytics.services.collector.useragent_service")
    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_create_new_session_session_id_not_found(
        self, mock_settings, mock_geoip, mock_useragent
    ):
        """When session_id is provided but not found in DB, create a new
        session reusing the provided session_id."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()
        mock_result.scalar_one_or_none.return_value = None
        mock_settings.anonymize_ip = False

        mock_geoip.lookup.return_value = _default_geo()
        mock_useragent.parse.return_value = _default_device_info()

        request = _make_mock_request()
        provided_id = "my-custom-session-id"

        session, is_new = await service.get_or_create_session(
            db=mock_db,
            request=request,
            session_id=provided_id,
        )

        assert is_new is True
        created_session = mock_db.add.call_args[0][0]
        assert created_session.session_id == provided_id

    @patch("analytics.services.collector.useragent_service")
    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_create_new_session_with_user_id(self, mock_settings, mock_geoip, mock_useragent):
        """When creating a new session with a user_id, it is stored."""
        service = CollectorService()
        mock_db = _mock_async_session()
        mock_settings.anonymize_ip = False

        mock_geoip.lookup.return_value = _default_geo()
        mock_useragent.parse.return_value = _default_device_info()

        user_id = uuid.uuid4()
        request = _make_mock_request()

        session, is_new = await service.get_or_create_session(
            db=mock_db,
            request=request,
            session_id=None,
            user_id=user_id,
        )

        assert is_new is True
        created_session = mock_db.add.call_args[0][0]
        assert created_session.user_id == user_id

    @patch("analytics.services.collector.useragent_service")
    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_create_new_session_unknown_ip_stored_as_none(
        self, mock_settings, mock_geoip, mock_useragent
    ):
        """When the client IP resolves to 'unknown', ip_address should be None."""
        service = CollectorService()
        mock_db = _mock_async_session()
        mock_settings.anonymize_ip = False

        mock_geoip.lookup.return_value = GeoLocation()
        mock_useragent.parse.return_value = DeviceInfo()

        request = _make_mock_request(client_host=None)

        session, is_new = await service.get_or_create_session(
            db=mock_db,
            request=request,
            session_id=None,
        )

        assert is_new is True
        created_session = mock_db.add.call_args[0][0]
        assert created_session.ip_address is None


@pytest.mark.asyncio
class TestCollectorServiceTrackEvent:
    """Tests for CollectorService.track_event."""

    async def test_creates_event_and_commits(self):
        """track_event should create an Event, add it to the DB, and commit."""
        service = CollectorService()
        mock_db = _mock_async_session()

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session.session_id = "test-session-id"

        await service.track_event(
            db=mock_db,
            session=mock_session,
            event_type="page_view",
            event_data={"key": "value"},
            page_url="https://example.com/page",
            page_title="Test Page",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

        created_event = mock_db.add.call_args[0][0]
        assert created_event.session_id == mock_session.id
        assert created_event.event_type == "page_view"
        assert created_event.event_data == {"key": "value"}
        assert created_event.page_url == "https://example.com/page"
        assert created_event.page_title == "Test Page"

    async def test_updates_session_last_seen(self):
        """track_event should update session.last_seen to a recent time."""
        service = CollectorService()
        mock_db = _mock_async_session()

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session.session_id = "test-session-id"
        mock_session.last_seen = datetime(2025, 1, 1)

        before = datetime.now(UTC)
        await service.track_event(
            db=mock_db,
            session=mock_session,
            event_type="click",
        )
        after = datetime.now(UTC)

        assert before <= mock_session.last_seen <= after

    async def test_creates_event_with_none_optional_fields(self):
        """track_event works when optional fields are None."""
        service = CollectorService()
        mock_db = _mock_async_session()

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session.session_id = "test-session-id"

        await service.track_event(
            db=mock_db,
            session=mock_session,
            event_type="custom_event",
            event_data=None,
            page_url=None,
            page_title=None,
        )

        created_event = mock_db.add.call_args[0][0]
        assert created_event.event_data is None
        assert created_event.page_url is None
        assert created_event.page_title is None


@pytest.mark.asyncio
class TestCollectorServiceTrackPixelOpen:
    """Tests for CollectorService.track_pixel_open."""

    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_pixel_found_creates_open_record(self, mock_settings, mock_geoip):
        """When the pixel is found, a PixelOpen record should be created and
        pixel stats updated."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()
        mock_settings.anonymize_ip = False

        pixel_id = uuid.uuid4()
        mock_pixel = MagicMock()
        mock_pixel.id = pixel_id
        mock_pixel.first_opened_at = datetime(2025, 6, 1)
        mock_pixel.last_opened_at = datetime(2025, 6, 1)
        mock_pixel.open_count = 5
        mock_pixel.pixel_key = "test-pixel-key"
        mock_result.scalar_one_or_none.return_value = mock_pixel

        mock_geoip.lookup.return_value = _default_geo()
        request = _make_mock_request()

        result = await service.track_pixel_open(
            db=mock_db,
            pixel_key="test-pixel-key",
            request=request,
        )

        assert result is mock_pixel
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

        # Verify PixelOpen record fields
        pixel_open = mock_db.add.call_args[0][0]
        assert pixel_open.pixel_id == pixel_id
        assert pixel_open.ip_address == "1.2.3.4"
        assert pixel_open.user_agent == "TestAgent/1.0"
        assert pixel_open.country == "US"
        assert pixel_open.city == "New York"

        # Verify stats updated
        assert mock_pixel.open_count == 6
        assert mock_pixel.last_opened_at is not None

    async def test_pixel_not_found_returns_none(self):
        """When the pixel is not found, return None without creating records."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()
        mock_result.scalar_one_or_none.return_value = None

        request = _make_mock_request()

        result = await service.track_pixel_open(
            db=mock_db,
            pixel_key="nonexistent-key",
            request=request,
        )

        assert result is None
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()

    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_first_open_sets_first_opened_at(self, mock_settings, mock_geoip):
        """When the pixel has never been opened before, first_opened_at
        should be set."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()
        mock_settings.anonymize_ip = False

        mock_pixel = MagicMock()
        mock_pixel.id = uuid.uuid4()
        mock_pixel.first_opened_at = None  # Never opened
        mock_pixel.last_opened_at = None
        mock_pixel.open_count = 0
        mock_pixel.pixel_key = "fresh-pixel"
        mock_result.scalar_one_or_none.return_value = mock_pixel

        mock_geoip.lookup.return_value = _default_geo()
        request = _make_mock_request()

        before = datetime.now(UTC)
        result = await service.track_pixel_open(
            db=mock_db,
            pixel_key="fresh-pixel",
            request=request,
        )
        after = datetime.now(UTC)

        assert result is mock_pixel
        assert mock_pixel.first_opened_at is not None
        assert before <= mock_pixel.first_opened_at <= after
        assert mock_pixel.last_opened_at is not None
        assert mock_pixel.open_count == 1

    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_subsequent_open_does_not_change_first_opened_at(self, mock_settings, mock_geoip):
        """When pixel already has a first_opened_at, it should not be changed."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()
        mock_settings.anonymize_ip = False

        original_first_opened = datetime(2025, 1, 1, 12, 0, 0)
        mock_pixel = MagicMock()
        mock_pixel.id = uuid.uuid4()
        mock_pixel.first_opened_at = original_first_opened
        mock_pixel.last_opened_at = datetime(2025, 6, 1)
        mock_pixel.open_count = 10
        mock_pixel.pixel_key = "existing-pixel"
        mock_result.scalar_one_or_none.return_value = mock_pixel

        mock_geoip.lookup.return_value = _default_geo()
        request = _make_mock_request()

        await service.track_pixel_open(
            db=mock_db,
            pixel_key="existing-pixel",
            request=request,
        )

        # first_opened_at must not have changed
        assert mock_pixel.first_opened_at == original_first_opened
        assert mock_pixel.open_count == 11

    @patch("analytics.services.collector.geoip_service")
    @patch("analytics.services.collector.settings")
    async def test_unknown_ip_stored_as_none(self, mock_settings, mock_geoip):
        """When client IP is 'unknown', ip_address on PixelOpen should be None."""
        service = CollectorService()
        mock_db, mock_result = _make_mock_db()
        mock_settings.anonymize_ip = False

        mock_pixel = MagicMock()
        mock_pixel.id = uuid.uuid4()
        mock_pixel.first_opened_at = datetime(2025, 1, 1)
        mock_pixel.open_count = 0
        mock_pixel.pixel_key = "ip-test-pixel"
        mock_result.scalar_one_or_none.return_value = mock_pixel

        mock_geoip.lookup.return_value = GeoLocation()
        request = _make_mock_request(client_host=None)

        await service.track_pixel_open(
            db=mock_db,
            pixel_key="ip-test-pixel",
            request=request,
        )

        pixel_open = mock_db.add.call_args[0][0]
        assert pixel_open.ip_address is None


@pytest.mark.asyncio
class TestCollectorServiceCreateCampaign:
    """Tests for CollectorService.create_campaign."""

    @patch("analytics.services.collector.generate_tracking_key")
    async def test_creates_campaign_with_all_fields(self, mock_gen_key):
        """create_campaign should create a Campaign with all provided fields."""
        mock_gen_key.return_value = "generated-tracking-key"
        service = CollectorService()
        mock_db = _mock_async_session()

        await service.create_campaign(
            db=mock_db,
            name="Black Friday",
            description="Annual sale",
            destination_url="https://shop.example.com/sale",
            extra_data={"discount": "20%"},
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

        campaign = mock_db.add.call_args[0][0]
        assert campaign.name == "Black Friday"
        assert campaign.description == "Annual sale"
        assert campaign.tracking_key == "generated-tracking-key"
        assert campaign.destination_url == "https://shop.example.com/sale"
        assert campaign.extra_data == {"discount": "20%"}

    @patch("analytics.services.collector.generate_tracking_key")
    async def test_creates_campaign_with_minimal_fields(self, mock_gen_key):
        """create_campaign should work with only the required name field."""
        mock_gen_key.return_value = "minimal-key"
        service = CollectorService()
        mock_db = _mock_async_session()

        await service.create_campaign(
            db=mock_db,
            name="Simple Campaign",
        )

        campaign = mock_db.add.call_args[0][0]
        assert campaign.name == "Simple Campaign"
        assert campaign.description is None
        assert campaign.destination_url is None
        assert campaign.extra_data is None
        assert campaign.tracking_key == "minimal-key"

    @patch("analytics.services.collector.generate_tracking_key")
    async def test_create_campaign_calls_generate_tracking_key(self, mock_gen_key):
        """create_campaign should use generate_tracking_key for the tracking_key."""
        mock_gen_key.return_value = "abc123"
        service = CollectorService()
        mock_db = _mock_async_session()

        await service.create_campaign(db=mock_db, name="Test")

        mock_gen_key.assert_called_once()


@pytest.mark.asyncio
class TestCollectorServiceCreatePixel:
    """Tests for CollectorService.create_pixel."""

    @patch("analytics.services.collector.generate_tracking_key")
    async def test_creates_pixel_with_all_fields(self, mock_gen_key):
        """create_pixel should create a Pixel with all provided fields."""
        mock_gen_key.return_value = "generated-pixel-key"
        service = CollectorService()
        mock_db = _mock_async_session()

        campaign_id = uuid.uuid4()

        await service.create_pixel(
            db=mock_db,
            campaign_id=campaign_id,
            recipient_email="user@example.com",
            recipient_id="user-123",
            extra_data={"template": "welcome"},
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

        pixel = mock_db.add.call_args[0][0]
        assert pixel.campaign_id == campaign_id
        assert pixel.pixel_key == "generated-pixel-key"
        assert pixel.recipient_email == "user@example.com"
        assert pixel.recipient_id == "user-123"
        assert pixel.extra_data == {"template": "welcome"}

    @patch("analytics.services.collector.generate_tracking_key")
    async def test_creates_pixel_with_minimal_fields(self, mock_gen_key):
        """create_pixel should work with only the required campaign_id."""
        mock_gen_key.return_value = "minimal-pixel-key"
        service = CollectorService()
        mock_db = _mock_async_session()

        campaign_id = uuid.uuid4()

        await service.create_pixel(
            db=mock_db,
            campaign_id=campaign_id,
        )

        pixel = mock_db.add.call_args[0][0]
        assert pixel.campaign_id == campaign_id
        assert pixel.pixel_key == "minimal-pixel-key"
        assert pixel.recipient_email is None
        assert pixel.recipient_id is None
        assert pixel.extra_data is None

    @patch("analytics.services.collector.generate_tracking_key")
    async def test_create_pixel_calls_generate_tracking_key(self, mock_gen_key):
        """create_pixel should use generate_tracking_key for the pixel_key."""
        mock_gen_key.return_value = "xyz789"
        service = CollectorService()
        mock_db = _mock_async_session()

        await service.create_pixel(db=mock_db, campaign_id=uuid.uuid4())

        mock_gen_key.assert_called_once()
