# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for authentication.

A tiny FastAPI application exposes one endpoint guarded by ``require_scopes``;
token validation is faked by the behave environment.
"""

import httpx
from behave import given, when
from billing.auth import AuthContext, require_scopes
from fastapi import Depends, FastAPI
from httpx import ASGITransport


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


@given('a protected endpoint requiring scope "{scope}"')
def step_protected_endpoint(context, scope):
    """Build a throw-away application with one endpoint protected by ``scope``."""
    protected_app = FastAPI()

    @protected_app.get("/protected")
    async def protected(auth: AuthContext = Depends(require_scopes(scope))):
        return {"user_id": auth.user_id, "scopes": auth.scopes}

    context.protected_client = httpx.AsyncClient(
        transport=ASGITransport(app=protected_app), base_url="http://testserver"
    )


@given('a token "{token}" with scopes "{scopes}"')
def step_register_token(context, token, scopes):
    """Make the fake token validation accept ``token`` with the given scopes."""
    context.register_token(token, scopes.split())


@when("I call the protected endpoint without token")
def step_call_without_token(context):
    """Call the protected endpoint with no Authorization header."""
    context.response = _run(context, context.protected_client.get("/protected"))


@when('I call the protected endpoint with token "{token}"')
def step_call_with_token(context, token):
    """Call the protected endpoint with the given bearer token."""
    context.response = _run(
        context,
        context.protected_client.get("/protected", headers={"Authorization": f"Bearer {token}"}),
    )
