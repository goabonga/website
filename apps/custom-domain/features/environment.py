# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: everything runs in-process, no external service is needed."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from custom_domain.main import app
from fakes import FakeDatabase
from httpx import ASGITransport, AsyncClient


def before_all(context):
    """Create the event loop shared by all scenarios."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)


def after_all(context):
    """Close the event loop."""
    context.loop.close()


def before_scenario(context, scenario):
    """Reset the per-scenario state."""
    context.app = app
    context.response = None
    context.token = None
    context.db = FakeDatabase()
    context.db.install(app)
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
    headers = dict(kwargs.pop("headers", {}))
    if context.token:
        headers["Authorization"] = f"Bearer {context.token}"

    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.request(method, path, headers=headers, **kwargs)

    context.response = context.loop.run_until_complete(send())
    return context.response


def start_patch(context, target, **kwargs):
    """Start a patcher that is stopped automatically after the scenario."""
    patcher = patch(target, **kwargs)
    mock = patcher.start()
    context.patchers.append(patcher)
    return mock


def authenticate(context, scopes, client_id="test-client", subject=None, error=None):
    """Make the auth dependencies accept (or reject) a JWT-shaped bearer token."""
    claims = {
        "sub": subject or str(uuid4()),
        "scope": " ".join(scopes),
        "client_id": client_id,
        "email": "user@example.com",
    }
    jwks = start_patch(context, "custom_domain.auth.dependencies.jwks_manager")
    introspection = start_patch(context, "custom_domain.auth.dependencies.introspection_client")
    exchange = start_patch(context, "custom_domain.auth.dependencies.token_exchange_client")
    jwks.is_configured = True
    exchange.is_configured = False
    introspection.validate_token_with_introspection = AsyncMock(
        return_value=claims, side_effect=error
    )
    introspection.validate_opaque_token = AsyncMock(return_value=claims, side_effect=error)
    context.token = "header.payload.signature"
    context.claims = claims
    return claims
