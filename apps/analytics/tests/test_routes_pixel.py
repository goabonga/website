# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.routes.pixel module."""

import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

EXPECTED_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def _make_mock_pixel(pixel_key="abc123"):
    """Create a mock Pixel object."""
    pixel = MagicMock()
    pixel.pixel_key = pixel_key
    pixel.id = uuid.uuid4()
    pixel.open_count = 1
    return pixel


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


class TestTrackPixelRoute:
    """Tests for GET /p/{pixel_key}.gif endpoint."""

    @pytest.mark.asyncio
    async def test_track_pixel_found(self, patched_app, mock_db):
        mock_pixel = _make_mock_pixel("test-pixel")

        with (
            patch("analytics.routes.pixel.collector_service") as mock_collector,
            patch("analytics.routes.pixel.set_request_context"),
            patch("analytics.routes.pixel.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_pixel_open = AsyncMock(return_value=mock_pixel)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/p/test-pixel.gif")

            assert resp.status_code == 200
            assert resp.content == EXPECTED_GIF
            assert resp.headers["content-type"] == "image/gif"
            assert resp.headers["cache-control"] == "no-cache, no-store, must-revalidate"
            assert resp.headers["pragma"] == "no-cache"
            assert resp.headers["expires"] == "0"
            assert resp.headers["x-content-type-options"] == "nosniff"

            mock_collector.track_pixel_open.assert_awaited_once()
            call_kwargs = mock_collector.track_pixel_open.call_args.kwargs
            assert call_kwargs["pixel_key"] == "test-pixel"

    @pytest.mark.asyncio
    async def test_track_pixel_not_found(self, patched_app, mock_db):
        with (
            patch("analytics.routes.pixel.collector_service") as mock_collector,
            patch("analytics.routes.pixel.set_request_context"),
            patch("analytics.routes.pixel.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_pixel_open = AsyncMock(return_value=None)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/p/unknown-pixel.gif")

            # Should still return a GIF (do not reveal pixel existence)
            assert resp.status_code == 200
            assert resp.content == EXPECTED_GIF
            assert resp.headers["content-type"] == "image/gif"

    @pytest.mark.asyncio
    async def test_track_pixel_sets_request_context(self, patched_app, mock_db):
        with (
            patch("analytics.routes.pixel.collector_service") as mock_collector,
            patch("analytics.routes.pixel.set_request_context") as mock_ctx,
            patch("analytics.routes.pixel.get_client_ip", return_value="10.0.0.1"),
        ):
            mock_collector.track_pixel_open = AsyncMock(return_value=None)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/p/ctx-pixel.gif")

            mock_ctx.assert_called_once_with(session_id="ctx-pixel", client_ip="10.0.0.1")


class TestTrackPixelNoExtensionRoute:
    """Tests for GET /p/{pixel_key} endpoint (no .gif extension)."""

    @pytest.mark.asyncio
    async def test_track_pixel_no_extension_found(self, patched_app, mock_db):
        mock_pixel = _make_mock_pixel("no-ext-pixel")

        with (
            patch("analytics.routes.pixel.collector_service") as mock_collector,
            patch("analytics.routes.pixel.set_request_context"),
            patch("analytics.routes.pixel.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_pixel_open = AsyncMock(return_value=mock_pixel)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/p/no-ext-pixel")

            assert resp.status_code == 200
            assert resp.content == EXPECTED_GIF
            assert resp.headers["content-type"] == "image/gif"

    @pytest.mark.asyncio
    async def test_track_pixel_no_extension_not_found(self, patched_app, mock_db):
        with (
            patch("analytics.routes.pixel.collector_service") as mock_collector,
            patch("analytics.routes.pixel.set_request_context"),
            patch("analytics.routes.pixel.get_client_ip", return_value="1.2.3.4"),
        ):
            mock_collector.track_pixel_open = AsyncMock(return_value=None)

            transport = ASGITransport(app=patched_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/p/missing")

            assert resp.status_code == 200
            assert resp.content == EXPECTED_GIF
