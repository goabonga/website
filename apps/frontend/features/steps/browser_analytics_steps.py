# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the analytics browser scenarios: a collector that receives the events over HTTP."""

import time

from behave import given, step, then
from e2e_support.server import LiveServer
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.routing import Route


def collector_app(events):
    """An analytics service that keeps the payloads posted to ``/collect``."""

    async def collect(request):
        events.append(await request.json())
        return Response(status_code=204)

    return Starlette(
        routes=[Route("/collect", collect, methods=["POST"])],
        middleware=[
            # the web client posts with credentials, so the origin must be echoed, not "*"
            Middleware(
                CORSMiddleware,
                allow_origin_regex=".*",
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ],
    )


@given("an analytics collector")
def analytics_collector(context):
    context.collected = []
    server = LiveServer(collector_app(context.collected)).start()
    context.servers.append(server)
    context.overrides["analytics_url"] = server.url


@step("the running application stops")
def application_stops(context):
    """Stop the application, which delivers the events it still holds."""
    application = next(s for s in context.servers if s.url == context.base_url)
    application.stop()
    context.servers.remove(application)


def received(context, event_type, path):
    return [
        payload
        for payload in context.collected
        if any(
            event.get("event_type") == event_type and event.get("page_url") == path
            for event in payload.get("events", [])
        )
    ]


@then('the analytics collector received a "{event_type}" event for "{path}"')
def received_event(context, event_type, path):
    """Wait for the event: the web client sends its events in batches, every few seconds."""
    deadline = time.monotonic() + context.e2e.settings.timeout / 1000
    while not received(context, event_type, path) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert received(context, event_type, path), f"the collector got {context.collected}"


@then('the analytics collector received no "{event_type}" event for "{path}"')
def received_no_event(context, event_type, path):
    assert not received(context, event_type, path), f"the collector got {context.collected}"
