# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.routes.collect module."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from analytics.routes.collect import CollectRequest, CollectResponse, EventPayload
from httpx import ASGITransport, AsyncClient


class TestEventPayload:
    """Tests for EventPayload model."""

    def test_minimal(self):
        payload = EventPayload(event_type="page_view")
        assert payload.event_type == "page_view"
        assert payload.event_data is None
        assert payload.page_url is None
        assert payload.page_title is None

    def test_full(self):
        payload = EventPayload(
            event_type="click",
            event_data={"element": "button"},
            page_url="https://example.com",
            page_title="Home",
        )
        assert payload.event_type == "click"
        assert payload.event_data == {"element": "button"}


class TestCollectRequest:
    """Tests for CollectRequest model."""

    def test_single_event(self):
        req = CollectRequest(events=[EventPayload(event_type="page_view")])
        assert len(req.events) == 1
        assert req.user_id is None

    def test_with_user_id(self):
        uid = uuid.uuid4()
        req = CollectRequest(
            events=[EventPayload(event_type="page_view")],
            user_id=uid,
        )
        assert req.user_id == uid


class TestCollectResponse:
    """Tests for CollectResponse model."""

    def test_serialization(self):
        resp = CollectResponse(success=True, session_id="test-sid", events_count=3)
        data = resp.model_dump()
        assert data["success"] is True
        assert data["session_id"] == "test-sid"
        assert data["events_count"] == 3


# ---------------------------------------------------------------------------
# Route handler tests using httpx AsyncClient
# ---------------------------------------------------------------------------


def _make_mock_session(session_id="test-session-id"):
    """Create a mock Session object."""
    session = MagicMock()
    session.session_id = session_id
    session.id = uuid.uuid4()
    return session


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def patched_app(mock_db):
    """Return the FastAPI app with get_db overridden."""
    from analytics.database import get_db
    from analytics.main import app

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


class TestCollectEventsRoute:
    """Tests for POST /collect endpoint."""

    @pytest.mark.asyncio
    async def test_collect_events_new_session(self, patched_app, mock_db):
        mock_session = _make_mock_session()

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, True))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/collect",
                    json={
                        "events": [{"event_type": "pageview", "page_url": "https://example.com"}]
                    },
                )

            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["session_id"] == "test-session-id"
            assert body["events_count"] == 1

            mock_collector.get_or_create_session.assert_awaited_once()
            mock_collector.track_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collect_events_existing_session(self, patched_app, mock_db):
        mock_session = _make_mock_session()

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/collect",
                    json={
                        "events": [
                            {"event_type": "pageview"},
                            {"event_type": "click", "event_data": {"el": "btn"}},
                        ]
                    },
                )

            assert resp.status_code == 200
            body = resp.json()
            assert body["events_count"] == 2
            # No cookie set since session is not new
            assert mock_collector.track_event.await_count == 2

    @pytest.mark.asyncio
    async def test_collect_events_with_cookie(self, patched_app, mock_db):
        mock_session = _make_mock_session("existing-sid")

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
                cookies={"ua_sid": "existing-sid"},
            ) as client:
                resp = await client.post(
                    "/collect",
                    json={"events": [{"event_type": "pageview"}]},
                )

            assert resp.status_code == 200
            call_kwargs = mock_collector.get_or_create_session.call_args
            assert call_kwargs.kwargs.get("session_id") == "existing-sid"

    @pytest.mark.asyncio
    async def test_collect_events_sets_cookie_when_new(self, patched_app, mock_db):
        mock_session = _make_mock_session("new-session")

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="10.0.0.1"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, True))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/collect",
                    json={"events": [{"event_type": "pageview"}]},
                )

            # Cookie should be set in response
            assert resp.status_code == 200
            set_cookie_headers = resp.headers.get_list("set-cookie")
            assert any("ua_sid" in c for c in set_cookie_headers)

    @pytest.mark.asyncio
    async def test_collect_events_multiple_events(self, patched_app, mock_db):
        mock_session = _make_mock_session()

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            events = [{"event_type": f"event_{i}"} for i in range(5)]

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/collect",
                    json={"events": events},
                )

            assert resp.status_code == 200
            assert resp.json()["events_count"] == 5
            assert mock_collector.track_event.await_count == 5


class TestCollectBeaconRoute:
    """Tests for GET /collect endpoint."""

    @pytest.mark.asyncio
    async def test_collect_beacon_basic(self, patched_app, mock_db):
        mock_session = _make_mock_session()

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/collect?t=pageview")

            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/gif"
            assert resp.headers["cache-control"] == "no-cache, no-store, must-revalidate"
            assert resp.headers["pragma"] == "no-cache"

    @pytest.mark.asyncio
    async def test_collect_beacon_with_event_data(self, patched_app, mock_db):
        mock_session = _make_mock_session()

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    '/collect?t=click&d={"button":"submit"}&u=https://example.com'
                )

            assert resp.status_code == 200
            call_kwargs = mock_collector.track_event.call_args
            assert call_kwargs.kwargs["event_data"] == {"button": "submit"}
            assert call_kwargs.kwargs["page_url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_collect_beacon_invalid_json_data(self, patched_app, mock_db):
        mock_session = _make_mock_session()

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/collect?t=click&d=not-valid-json")

            assert resp.status_code == 200
            call_kwargs = mock_collector.track_event.call_args
            assert call_kwargs.kwargs["event_data"] is None

    @pytest.mark.asyncio
    async def test_collect_beacon_new_session_sets_cookie(self, patched_app, mock_db):
        mock_session = _make_mock_session("beacon-session")

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, True))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/collect?t=pageview")

            assert resp.status_code == 200
            set_cookie_headers = resp.headers.get_list("set-cookie")
            assert any("ua_sid" in c for c in set_cookie_headers)

    @pytest.mark.asyncio
    async def test_collect_beacon_existing_session_no_cookie(self, patched_app, mock_db):
        mock_session = _make_mock_session()

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/collect?t=pageview")

            assert resp.status_code == 200
            set_cookie_headers = resp.headers.get_list("set-cookie")
            assert not any("ua_sid" in c for c in set_cookie_headers)

    @pytest.mark.asyncio
    async def test_collect_beacon_returns_gif_bytes(self, patched_app, mock_db):
        import base64

        mock_session = _make_mock_session()
        expected_gif = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

        with (
            patch("analytics.routes.collect.collector_service") as mock_collector,
            patch("analytics.routes.collect.set_request_context"),
            patch("analytics.routes.collect.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.get_or_create_session = AsyncMock(return_value=(mock_session, False))
            mock_collector.track_event = AsyncMock()

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/collect?t=pageview")

            assert resp.content == expected_gif
