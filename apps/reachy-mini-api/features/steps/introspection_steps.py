# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the token introspection feature."""

from unittest.mock import AsyncMock, PropertyMock, patch
from uuid import uuid4

from behave import given, then
from reachy_mini_api.auth import introspection_client


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


@given("token introspection is configured")
def step_introspection_configured(context):
    """Mark the introspection client as configured, without a real client secret."""
    start_patch(
        context,
        patch.object(
            type(introspection_client),
            "is_configured",
            new_callable=PropertyMock,
            return_value=True,
        ),
    )


@given('the introspection endpoint reports tokens as "{state}" with the scopes "{scopes}"')
def step_introspection_reports(context, state, scopes):
    """Fake the introspection response."""
    response = {"active": state == "active", "sub": str(uuid4()), "scope": scopes}
    context.introspect = AsyncMock(return_value=response)
    start_patch(
        context, patch.object(introspection_client, "_introspect_request", context.introspect)
    )


@given("the introspection endpoint is unreachable")
def step_introspection_unreachable(context):
    """Make every introspection call fail."""
    context.introspect = AsyncMock(side_effect=ConnectionError("unreachable"))
    start_patch(
        context, patch.object(introspection_client, "_introspect_request", context.introspect)
    )


@given("a Redis cache is available")
def step_redis_available(context):
    """Use an in-memory Redis for the introspection cache."""
    redis = FakeRedis()
    start_patch(
        context,
        patch.object(introspection_client, "_get_redis_client", AsyncMock(return_value=redis)),
    )


@given('I use the opaque token "{token}"')
def step_opaque_token(context, token):
    """Send an opaque (non-JWT) bearer token."""
    context.auth_headers = {"Authorization": f"Bearer {token}"}


@then("the introspection endpoint should have been called {count:d} time")
def step_introspection_calls(context, count):
    """Check how many times the introspection endpoint was queried."""
    assert context.introspect.await_count == count, context.introspect.await_count
