# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: drives the ASGI application in-process.

No server, database or Redis is started. Requests go straight to the ASGI
application through httpx, and external collaborators are replaced by fakes
inside the step modules.
"""

import asyncio

import httpx


def before_all(context):
    from knowledge.main import app

    context.app = app

    def call(method, path, **kwargs):
        async def run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(run())

    context.call = call


def before_scenario(context, scenario):
    context.response = None
    context.app.dependency_overrides.clear()


def after_scenario(context, scenario):
    context.app.dependency_overrides.clear()
