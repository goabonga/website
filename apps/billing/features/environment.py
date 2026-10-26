# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks for the in-process BDD scenarios.

Everything runs inside the test process: the FastAPI application is called
through an ASGI transport, so no server, PostgreSQL, Redis or network is
needed.
"""

import asyncio

import httpx
from billing.main import app
from httpx import ASGITransport


async def _create_async_client(headers=None):
    """Create an httpx AsyncClient using ASGI transport."""
    return httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers or {},
    )


# -- Behave hooks -------------------------------------------------------------


def before_all(context):
    """Set up the event loop, the fakes and the HTTP clients."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)

    context.anon_client = context.loop.run_until_complete(_create_async_client())


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
    context.created_ids = {}  # Track created entity IDs for cross-step reference


def after_all(context):
    """Tear down clients, patches and event loop."""
    context.loop.run_until_complete(context.anon_client.aclose())
    context.loop.close()
