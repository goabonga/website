# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: drives ASGI applications in-process.

No server, database or Redis is started. Requests go straight to the ASGI
application through httpx, and external collaborators are replaced by fakes
inside the step modules.
"""

import asyncio

import httpx


def call_app(app, method, path, **kwargs):
    """Send one request to an ASGI application and return the httpx response."""

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def before_all(context):
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


def after_scenario(context, scenario):
    context.app.dependency_overrides.clear()
    context.internal_app.dependency_overrides.clear()
