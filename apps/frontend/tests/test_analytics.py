# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from frontend.analytics import AnalyticsTracker, get_client_ip
from frontend.config import Settings
from frontend.main import create_app

SettingsFactory = Callable[..., Settings]


class Collector:
    """In-memory analytics service recording what it receives."""

    def __init__(self, status: int = 204, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.posted: list[tuple[str, dict]] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self.error is not None:
            raise self.error
        self.posted.append((str(request.url), json.loads(request.content)))
        return httpx.Response(self.status)

    @property
    def events(self) -> list[dict]:
        return [payload["events"][0] for _, payload in self.posted]


@pytest.fixture
def collector() -> Collector:
    return Collector()


def make_request(headers: dict[str, str] | None = None, client=("9.9.9.9", 1234)) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client,
    }
    return Request(scope)


def test_analytics_url_default_is_empty(monkeypatch) -> None:
    monkeypatch.delenv("ANALYTICS_URL", raising=False)
    assert Settings(_env_file=None).analytics_url == ""


def test_not_configured_ignores_events() -> None:
    tracker = AnalyticsTracker()
    assert tracker.is_configured is False
    tracker.track("page_view_server", page_url="/")
    assert tracker._queue == []


def test_endpoint_strips_trailing_slash() -> None:
    tracker = AnalyticsTracker("https://ua.test/")
    assert tracker.is_configured is True
    assert tracker._endpoint == "https://ua.test/collect"


async def test_flush_posts_each_event(collector: Collector) -> None:
    tracker = AnalyticsTracker("https://ua.test", transport=collector.transport)
    tracker.track("page_view_server", page_url="/a", ip_address="1.2.3.4")
    tracker.track("click", event_data={"k": "v"}, user_id="u1", session_id="s1")
    assert len(tracker._queue) == 2
    await tracker.close()
    assert tracker._queue == []
    assert [url for url, _ in collector.posted] == ["https://ua.test/collect"] * 2
    first, second = (payload for _, payload in collector.posted)
    assert first == {
        "events": [{"event_type": "page_view_server", "page_url": "/a"}],
        "ip_address": "1.2.3.4",
    }
    assert second == {
        "events": [{"event_type": "click", "event_data": {"k": "v"}}],
        "user_id": "u1",
        "session_id": "s1",
    }


async def test_flush_tolerates_http_errors() -> None:
    collector = Collector(status=500)
    tracker = AnalyticsTracker("https://ua.test", transport=collector.transport)
    tracker.track("page_view_server")
    await tracker.close()
    assert tracker._queue == []
    assert len(collector.posted) == 1


async def test_flush_tolerates_transport_errors() -> None:
    collector = Collector(error=httpx.ConnectError("down"))
    tracker = AnalyticsTracker("https://ua.test", transport=collector.transport)
    tracker.track("page_view_server")
    tracker.track("page_view_server")
    await tracker.close()
    assert tracker._queue == []


async def test_flush_without_events_sends_nothing(collector: Collector) -> None:
    tracker = AnalyticsTracker("https://ua.test", transport=collector.transport)
    await tracker.flush()
    assert collector.posted == []


async def test_full_queue_triggers_flush(collector: Collector) -> None:
    tracker = AnalyticsTracker("https://ua.test", transport=collector.transport)
    for _ in range(10):
        tracker.track("e")
    await asyncio.sleep(0.05)  # let the flush task run
    assert len(collector.posted) == 10
    assert tracker._queue == []
    await tracker.close()


async def test_delayed_flush_after_interval(collector: Collector) -> None:
    tracker = AnalyticsTracker("https://ua.test", transport=collector.transport)
    tracker._flush_interval = 0.01
    tracker.track("e")
    assert collector.posted == []
    await asyncio.sleep(0.1)
    assert len(collector.posted) == 1
    await tracker.close()


async def test_close_cancels_the_pending_flush_and_sends_the_events(collector: Collector) -> None:
    tracker = AnalyticsTracker("https://ua.test", transport=collector.transport)
    tracker.track("e")
    task = tracker._flush_task
    assert task is not None and not task.done()
    await tracker.close()
    assert task.cancelled()
    assert len(collector.posted) == 1


def test_client_ip_prefers_forwarded_for() -> None:
    request = make_request({"X-Forwarded-For": "1.1.1.1, 2.2.2.2", "X-Real-IP": "3.3.3.3"})
    assert get_client_ip(request) == "1.1.1.1"


def test_client_ip_falls_back_to_real_ip_then_peer() -> None:
    assert get_client_ip(make_request({"X-Real-IP": "3.3.3.3"})) == "3.3.3.3"
    assert get_client_ip(make_request()) == "9.9.9.9"
    assert get_client_ip(make_request(client=None)) is None


async def test_middleware_tracks_page_views(
    make_settings: SettingsFactory, collector: Collector
) -> None:
    app = create_app(make_settings(analytics_url="https://ua.test"), collector.transport)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://frontend.test"
    ) as http:
        await http.get("/login", headers={"X-Forwarded-For": "4.4.4.4"})
        await http.get("/health")
        await http.get("/static/assets/index.js")
    await app.state.analytics.close()
    assert collector.events == [
        {"event_type": "page_view_server", "page_url": "/login"},
        {"event_type": "page_view_server", "page_url": "/health"},
    ]
    assert collector.posted[0][1]["ip_address"] == "4.4.4.4"


async def test_middleware_sends_nothing_when_not_configured(
    make_settings: SettingsFactory, collector: Collector
) -> None:
    app = create_app(make_settings(), collector.transport)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://frontend.test"
    ) as http:
        response = await http.get("/")
    await app.state.analytics.close()
    assert response.status_code == 200
    assert collector.posted == []


async def test_analytics_failure_does_not_affect_the_response(
    make_settings: SettingsFactory,
) -> None:
    collector = Collector(error=httpx.ConnectError("down"))
    app = create_app(make_settings(analytics_url="https://ua.test"), collector.transport)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://frontend.test"
    ) as http:
        response = await http.get("/health")
    await app.state.analytics.close()
    assert response.json() == {"status": "healthy"}


def test_shutdown_flushes_pending_events(
    make_settings: SettingsFactory, collector: Collector
) -> None:
    app = create_app(make_settings(analytics_url="https://ua.test"), collector.transport)
    with TestClient(app) as client:
        client.get("/pricing")
        assert collector.posted == []
    assert collector.events == [{"event_type": "page_view_server", "page_url": "/pricing"}]


def test_each_application_owns_its_tracker(make_settings: SettingsFactory) -> None:
    first = create_app(make_settings(analytics_url="https://ua.test"))
    second = create_app(make_settings())
    assert first.state.analytics is not second.state.analytics
    assert first.state.analytics.is_configured is True
    assert second.state.analytics.is_configured is False
