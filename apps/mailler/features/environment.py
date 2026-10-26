# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run in-process: requests go through httpx's ASGI transport straight
into the FastAPI application, so no server, identity provider, database or
broker is needed. The token validation clients are replaced by a lookup table
filled by the authentication steps.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import APIRouter, Depends
from httpx import ASGITransport
from mailler.auth import AuthContext, require_scopes
from mailler.auth.introspection import TokenRevokedError
from mailler.config import settings
from mailler.main import app

# Probe routes protected by scopes, so authentication can be exercised before
# the feature routes exist and independently of them.
probe = APIRouter(prefix="/__probe")


@probe.get("/read")
async def probe_read(auth: AuthContext = Depends(require_scopes("mailler:read"))):
    return {"user_id": auth.user_id, "scopes": auth.scopes}


@probe.get("/client")
async def probe_client(auth: AuthContext = Depends(require_scopes("mailler:read"))):
    return {"client_id": auth.client_id, "is_admin": auth.is_admin}


@probe.get("/send")
async def probe_send(auth: AuthContext = Depends(require_scopes("mailler:send"))):
    return {"user_id": auth.user_id, "scopes": auth.scopes}


def _validate(context):
    """Build the token validation function backed by ``context.token_claims``."""

    async def validate(token):
        if token in context.revoked_tokens:
            raise TokenRevokedError("revoked")
        try:
            return context.token_claims[token]
        except KeyError:
            raise ValueError("unknown token") from None

    return validate


def before_all(context):
    """Create the event loop, replace token validation and build the client."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    # The CORS middleware keeps a reference to the configured list, so extending
    # it in place is enough for the running application.
    settings.cors_origins.append("https://frontend.example")

    context.token_claims = {}
    context.revoked_tokens = set()

    context._patchers = [
        patch("mailler.auth.dependencies.jwks_manager"),
        patch("mailler.auth.dependencies.introspection_client"),
        patch("mailler.auth.dependencies.token_exchange_client"),
    ]
    context.jwks, context.introspection, context.exchange = [p.start() for p in context._patchers]
    context.exchange.is_configured = False
    validate = _validate(context)
    context.introspection.validate_token_with_introspection = AsyncMock(side_effect=validate)
    context.introspection.validate_opaque_token = AsyncMock(side_effect=validate)

    app.include_router(probe)
    context.client = httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
    context.created_ids = {}
    context.token_claims.clear()
    context.revoked_tokens.clear()
    context.jwks.is_configured = True
    context.client.headers.pop("Authorization", None)


def after_all(context):
    """Close the client, stop the patches and close the event loop."""
    context.loop.run_until_complete(context.client.aclose())
    for patcher in context._patchers:
        patcher.stop()
    context.loop.close()
