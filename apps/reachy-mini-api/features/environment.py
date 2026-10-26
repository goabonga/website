# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment configuration for BDD tests (in-process, no infrastructure)."""

import asyncio
import os
import sys

# The issuer must be set before the application is imported so that the OAuth2
# scheme is created with the settings.
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from reachy_mini_api.config import settings  # noqa: E402
from reachy_mini_api.logging import setup_logging  # noqa: E402
from reachy_mini_api.main import app  # noqa: E402


def send_request(context, method, path, headers=None):
    """Send a request to the current ASGI application and store the response."""

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.request(method, path, headers=headers or context.auth_headers)

    context.response = context.loop.run_until_complete(make_request())


def before_all(context):
    """Create the event loop and expose the ASGI application."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.main_app = app
    context.send_request = lambda method, path, headers=None: send_request(
        context, method, path, headers
    )


def after_all(context):
    """Close the event loop."""
    context.loop.close()


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.app = context.main_app
    context.response = None
    context.auth_headers = {}
    context.setting_backup = {}
    context.patchers = []
    context.ws = None
    context.last_message = None


def after_scenario(context, scenario):
    """Restore overridden settings, patches and the standard streams."""
    if context.ws is not None:
        context.ws.__exit__(None, None, None)
        context.ws = None
    for patcher in reversed(context.patchers):
        patcher.stop()
    for name, value in context.setting_backup.items():
        setattr(settings, name, value)
    saved = getattr(context, "saved_streams", None)
    if saved:
        sys.stdout, sys.stderr = saved
        context.saved_streams = None
        setup_logging()
