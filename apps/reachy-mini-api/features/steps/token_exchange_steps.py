# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the token exchange feature."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from behave import given, then
from reachy_mini_api.auth import introspection_client, jwks_manager, token_exchange_client
from reachy_mini_api.config import settings


class FakeRedis:
    """In-memory stand-in for the asynchronous Redis client."""

    def __init__(self):
        self.store = {}

    async def get(self, key):
        """Return the cached value."""
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        """Store a value, ignoring the expiry."""
        self.store[key] = value


def start_patch(context, patcher):
    """Start a patcher and register it for the end of the scenario."""
    patcher.start()
    context.patchers.append(patcher)


def override_setting(context, name, value):
    """Override a setting for the duration of the scenario."""
    context.setting_backup.setdefault(name, getattr(settings, name))
    setattr(settings, name, value)


def fake_auth_server(context, status_code, body):
    """Replace the HTTP calls of the exchange client by an in-process auth server."""
    response = MagicMock(status_code=status_code, content=b"{}")
    response.json.return_value = body
    context.exchange_post = AsyncMock(return_value=response)
    http_client = SimpleNamespace(post=context.exchange_post)
    start_patch(
        context,
        patch.object(
            token_exchange_client, "_get_http_client", AsyncMock(return_value=http_client)
        ),
    )


@given("token exchange is configured with a confidential client")
def step_exchange_configured(context):
    """Configure the confidential client and fake the discovery and introspection calls."""
    override_setting(context, "oauth2_client_id", "behave-client")
    override_setting(context, "oauth2_client_secret", "behave-secret")
    config = {"token_endpoint": "https://auth.test.example.com/oauth2/token"}
    start_patch(
        context, patch.object(jwks_manager, "fetch_issuer_config", AsyncMock(return_value=config))
    )
    introspection = AsyncMock(return_value={"active": True})
    start_patch(context, patch.object(introspection_client, "_introspect_request", introspection))


@given("the auth server answers the token exchange with status {status_code:d}")
def step_exchange_ok(context, status_code):
    """The auth server grants the requested scopes."""
    fake_auth_server(context, status_code, {"access_token": "", "scope": "reachy:reports:read"})


@given('the auth server answers the token exchange with the error "{error}"')
def step_exchange_error(context, error):
    """The auth server refuses the exchange."""
    fake_auth_server(context, 400, {"error": error, "error_description": "refused"})


@given("a Redis cache is available for token exchange")
def step_redis_available(context):
    """Use an in-memory Redis for the exchange cache."""
    redis = FakeRedis()
    start_patch(
        context,
        patch.object(token_exchange_client, "_get_redis_client", AsyncMock(return_value=redis)),
    )


@given('I use an active opaque token with the scopes "{scopes}"')
def step_opaque_token(context, scopes):
    """Send an opaque token that the introspection endpoint reports as active."""
    response = {"active": True, "sub": str(uuid4()), "scope": scopes}
    start_patch(
        context,
        patch.object(introspection_client, "_introspect_request", AsyncMock(return_value=response)),
    )
    context.auth_headers = {"Authorization": "Bearer ory_pat_behave"}


@then('the auth server should have been asked for the scope "{scope}"')
def step_asked_for_scope(context, scope):
    """Check the scope sent in the exchange request."""
    data = context.exchange_post.await_args.kwargs["data"]
    assert data["scope"] == scope, data
    assert data["grant_type"] == token_exchange_client.GRANT_TYPE, data


@then("the auth server should have received {count:d} exchange request")
def step_exchange_count(context, count):
    """Check how many exchange requests reached the auth server."""
    assert context.exchange_post.await_count == count, context.exchange_post.await_count
