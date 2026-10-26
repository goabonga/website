# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: everything runs in-process, no external service is needed."""

import asyncio

from custom_domain.main import app
from httpx import ASGITransport, AsyncClient


def before_all(context):
    """Create the event loop shared by all scenarios."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.app = app


def after_all(context):
    """Close the event loop."""
    context.loop.close()


def before_scenario(context, scenario):
    """Reset the per-scenario state."""
    context.response = None
    context.patchers = []
    context.cleanups = []


def after_scenario(context, scenario):
    """Undo patches, dependency overrides and registered cleanups."""
    for patcher in reversed(context.patchers):
        patcher.stop()
    for cleanup in reversed(context.cleanups):
        cleanup()
    app.dependency_overrides.clear()


def http_request(context, method, path, **kwargs):
    """Send a request to the ASGI application and keep the response on the context."""

    async def send():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    context.response = context.loop.run_until_complete(send())
    return context.response
