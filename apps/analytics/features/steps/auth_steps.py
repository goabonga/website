# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the OAuth2 authentication feature.

The scenarios build a small application whose routes use the real
``get_current_user`` and ``require_scopes`` dependencies. Token validation is
replaced by in-memory fakes, so no OIDC server or Redis is needed.
"""

from types import SimpleNamespace
from unittest.mock import patch

from analytics.auth import User, get_current_user, jwt_validator, require_scopes
from analytics.auth.jwt import TokenRevokedError
from analytics.auth.token_exchange import TokenExchangeError
from analytics.config import settings
from behave import given, when
from fastapi import Depends, FastAPI

USER_ID = "00000000-0000-0000-0000-000000000001"


def build_protected_app():
    """Create an application with one route per protection level."""
    app = FastAPI()

    @app.get("/read")
    async def read(user: User = Depends(require_scopes("analytics:read"))):
        return {
            "id": str(user.id),
            "scopes": str(user.scopes),
            "machine": user.is_machine_client,
        }

    @app.get("/write")
    async def write(user: User = Depends(require_scopes("analytics:write"))):
        return {"id": str(user.id), "scopes": str(user.scopes)}

    @app.get("/me")
    async def me(user: User = Depends(get_current_user)):
        return {"id": str(user.id), "email": user.email}

    return app


def _start_patch(context, patcher):
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('a protected application with the routes "/read" and "/write"')
def step_protected_app(context):
    context.protected_app = build_protected_app()
    context.tokens = {}

    async def fake_validate(token):
        if token == "revoked":
            raise TokenRevokedError("revoked")
        if token not in context.tokens:
            raise ValueError("unknown token")
        return context.tokens[token]

    _start_patch(
        context,
        patch.object(jwt_validator, "validate_token_with_introspection", fake_validate),
    )


@given('the token "{token}" grants the scopes "{scopes}"')
def step_token_scopes(context, token, scopes):
    context.tokens[token] = {"sub": USER_ID, "scope": scopes}


@given('the token "{token}" is issued to the client "{client}" with the scopes "{scopes}"')
def step_machine_token(context, token, client, scopes):
    context.tokens[token] = {"sub": client, "scope": scopes}


@given('the token "{token}" belongs to the user "{email}" with the scopes "{scopes}"')
def step_user_token(context, token, email, scopes):
    context.tokens[token] = {"sub": USER_ID, "email": email, "scope": scopes}


def _configure_exchange(context, validate):
    exchange = SimpleNamespace(is_configured=True, validate_token_scopes=validate)
    _start_patch(context, patch("analytics.auth.dependencies.token_exchange_client", exchange))
    context.tokens["anything"] = {"sub": USER_ID, "scope": ""}


@given('token exchange is configured and grants "{scopes}"')
def step_exchange_grants(context, scopes):
    async def validate(token, required):
        return {"scope": scopes}

    _configure_exchange(context, validate)


@given('token exchange is configured and answers "{error_code}"')
def step_exchange_error(context, error_code):
    async def validate(token, required):
        raise TokenExchangeError("refused", error_code=error_code)

    _configure_exchange(context, validate)


@given("no OAuth2 issuer is configured")
def step_no_issuer(context):
    previous = settings.oauth2_issuer
    settings.oauth2_issuer = ""
    context.add_cleanup(setattr, settings, "oauth2_issuer", previous)


def _request(context, path, token):
    from httpx import ASGITransport, AsyncClient

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.protected_app), base_url="http://test"
        ) as client:
            return await client.get(path, headers=headers)

    context.response = context.loop.run_until_complete(make_request())
    context.response_json = None


@when('I request the protected route "{path}" without a token')
def step_request_without_token(context, path):
    _request(context, path, None)


@when('I request the protected route "{path}" with the token "{token}"')
def step_request_with_token(context, path, token):
    _request(context, path, token)
