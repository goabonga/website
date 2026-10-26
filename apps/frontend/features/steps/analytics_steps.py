# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the analytics feature: an in-memory analytics service."""

import json

import httpx
from behave import given, then, when


class FakeAnalyticsService:
    """Records the events posted to it, or fails every delivery."""

    def __init__(self) -> None:
        self.failing = False
        self.calls: list[tuple[str, dict]] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self.failing:
            raise httpx.ConnectError("analytics service is down")
        self.calls.append((str(request.url), json.loads(request.content)))
        return httpx.Response(204)


@given("an analytics service")
def step_service(context) -> None:
    context.analytics = FakeAnalyticsService()
    context.analytics_transport = context.analytics.transport


@given("the analytics service is failing")
def step_service_failing(context) -> None:
    context.analytics.failing = True


@when("the application stops")
def step_stop(context) -> None:
    context.stop_app()


@then('the analytics service received a "{event_type}" event for "{path}"')
def step_received_event(context, event_type: str, path: str) -> None:
    events = [payload["events"][0] for _, payload in context.analytics.calls]
    assert {"event_type": event_type, "page_url": path} in events, events


@then("the analytics service received {count:d} event")
@then("the analytics service received {count:d} events")
def step_received_count(context, count: int) -> None:
    assert len(context.analytics.calls) == count, context.analytics.calls


@then('the analytics service received the address "{address}"')
def step_received_address(context, address: str) -> None:
    assert [p.get("ip_address") for _, p in context.analytics.calls] == [address]


@then('the analytics service was called on "{url}"')
def step_called_on(context, url: str) -> None:
    assert [u for u, _ in context.analytics.calls] == [url]
