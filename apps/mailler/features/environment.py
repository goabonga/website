# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run in-process: requests go through httpx's ASGI transport straight
into the FastAPI application, so no server, database or broker is needed.
"""

import asyncio

import httpx
from httpx import ASGITransport
from mailler.config import settings
from mailler.main import app


def before_all(context):
    """Create the event loop and the HTTP client."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    # The CORS middleware keeps a reference to the configured list, so extending
    # it in place is enough for the running application.
    settings.cors_origins.append("https://frontend.example")
    context.client = httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
    context.created_ids = {}


def after_all(context):
    """Close the client and the event loop."""
    context.loop.run_until_complete(context.client.aclose())
    context.loop.close()
