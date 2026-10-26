# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment.

The in-process scenarios start no server, database or Redis: requests go straight to
the ASGI application through httpx, and external collaborators are replaced by fakes
inside the step modules.

The scenarios tagged ``@browser`` drive a real browser against the application served on
a local port (see ``browser_stack``); they are skipped when no browser is available.
"""

import asyncio

import httpx
from e2e_support import behave_hooks as e2e


def call_app(app, method, path, **kwargs):
    """Send one request to an ASGI application and return the httpx response."""

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def before_all(context):
    e2e.before_all(context)

    from knowledge.internal import internal_app
    from knowledge.main import app

    context.app = app
    context.internal_app = internal_app
    context.call_app = call_app
    context.call = lambda method, path, **kwargs: call_app(app, method, path, **kwargs)


def before_scenario(context, scenario):
    context.response = None
    context.app.dependency_overrides.clear()
    context.internal_app.dependency_overrides.clear()
    e2e.before_scenario(context, scenario, base_url=lambda: start_browser_stack(context))


def start_browser_stack(context):
    import browser_stack

    return browser_stack.begin_scenario(context)


def after_scenario(context, scenario):
    e2e.after_scenario(context, scenario)
    context.app.dependency_overrides.clear()
    context.internal_app.dependency_overrides.clear()


def after_all(context):
    e2e.after_all(context)
