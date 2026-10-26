# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.routes.track module."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _make_mock_campaign(tracking_key="tk-abc", destination_url="https://example.com"):
    """Create a mock Campaign object."""
    campaign = MagicMock()
    campaign.tracking_key = tracking_key
    campaign.destination_url = destination_url
    campaign.id = uuid.uuid4()
    campaign.name = "Test Campaign"
    return campaign


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


class TestTrackLinkRoute:
    """Tests for GET /t/{tracking_key} endpoint."""

    @pytest.mark.asyncio
    async def test_track_link_with_campaign_destination(self, patched_app, mock_db):
        mock_campaign = _make_mock_campaign(destination_url="https://dest.example.com")

        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=mock_campaign)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/t/tk-abc")

            assert resp.status_code == 302
            location = resp.headers["location"]
            assert location.startswith("https://dest.example.com")
            # utm_content should be added since campaign exists
            assert "utm_content=tk-abc" in location

    @pytest.mark.asyncio
    async def test_track_link_with_url_override(self, patched_app, mock_db):
        mock_campaign = _make_mock_campaign()

        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=mock_campaign)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/t/tk-abc?url=https://override.example.com")

            assert resp.status_code == 302
            location = resp.headers["location"]
            assert "override.example.com" in location

    @pytest.mark.asyncio
    async def test_track_link_campaign_not_found_fallback(self, patched_app, mock_db):
        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=None)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/t/unknown-key")

            assert resp.status_code == 302
            location = resp.headers["location"]
            assert "goabonga.com" in location

    @pytest.mark.asyncio
    async def test_track_link_preserves_utm_params(self, patched_app, mock_db):
        mock_campaign = _make_mock_campaign(destination_url="https://dest.example.com")

        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=mock_campaign)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get(
                    "/t/tk-abc?utm_source=newsletter&utm_medium=email&utm_campaign=spring"
                )

            assert resp.status_code == 302
            location = resp.headers["location"]
            assert "utm_source=newsletter" in location
            assert "utm_medium=email" in location
            assert "utm_campaign=spring" in location

    @pytest.mark.asyncio
    async def test_track_link_utm_content_not_overridden(self, patched_app, mock_db):
        mock_campaign = _make_mock_campaign(destination_url="https://dest.example.com")

        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=mock_campaign)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/t/tk-abc?utm_content=custom-content")

            assert resp.status_code == 302
            location = resp.headers["location"]
            # The provided utm_content should be used, not the tracking key
            assert "utm_content=custom-content" in location

    @pytest.mark.asyncio
    async def test_track_link_utm_appended_with_ampersand(self, patched_app, mock_db):
        mock_campaign = _make_mock_campaign(
            destination_url="https://dest.example.com?existing=param"
        )

        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=mock_campaign)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/t/tk-abc?utm_source=test")

            assert resp.status_code == 302
            location = resp.headers["location"]
            # Should use & since destination already has ?
            assert "existing=param&utm_source=test" in location

    @pytest.mark.asyncio
    async def test_track_link_sets_request_context(self, patched_app, mock_db):
        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context") as mock_ctx,
            patch("analytics.routes.track.get_client_ip", return_value="10.0.0.1"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=None)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                await client.get("/t/context-key")

            mock_ctx.assert_called_once_with(session_id="context-key", client_ip="10.0.0.1")

    @pytest.mark.asyncio
    async def test_track_link_no_utm_when_no_params_and_no_campaign(self, patched_app, mock_db):
        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=None)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/t/no-camp")

            assert resp.status_code == 302
            location = resp.headers["location"]
            # No campaign, no utm params -> fallback URL with no extra params
            assert location == "https://goabonga.com"

    @pytest.mark.asyncio
    async def test_track_link_campaign_no_destination_url(self, patched_app, mock_db):
        mock_campaign = _make_mock_campaign(destination_url=None)

        with (
            patch("analytics.routes.track.collector_service") as mock_collector,
            patch("analytics.routes.track.set_request_context"),
            patch("analytics.routes.track.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_campaign_click = AsyncMock(return_value=mock_campaign)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/t/tk-no-dest")

            assert resp.status_code == 302
            location = resp.headers["location"]
            assert "goabonga.com" in location
