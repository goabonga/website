# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the OAuth2 client credentials feature."""

from unittest.mock import patch

import httpx
from behave import given, then, when
from webhooks import auth
from webhooks.config import settings

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _set_setting(context, name, value):
    context.setting_backup.setdefault(name, getattr(settings, name))
    setattr(settings, name, value)


def _reset_client():
    """Forget any cached token between scenarios."""
    auth.oauth2_client._token = None
    auth.oauth2_client._expires_at = 0


@given("OAuth2 client credentials are not configured")
def step_oauth2_not_configured(context):
    _reset_client()
    _set_setting(context, "oauth2_token_url", "")
    _set_setting(context, "oauth2_client_id", "")
    _set_setting(context, "oauth2_client_secret", "")


@given("OAuth2 client credentials are configured")
def step_oauth2_configured(context):
    _reset_client()
    _set_setting(context, "oauth2_token_url", "https://auth.test/token")
    _set_setting(context, "oauth2_client_id", "webhooks")
    _set_setting(context, "oauth2_client_secret", "not-a-real-secret")


def _install_token_endpoint(context, handler):
    """Route the token request of the auth module to an in-process fake."""
    context.token_requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        context.token_requests.append(request)
        return handler(request)

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(respond)
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    patcher = patch("webhooks.auth.httpx.AsyncClient", side_effect=factory)
    patcher.start()
    context.token_patcher = patcher


@given('the token endpoint issues the access token "{token}"')
def step_token_endpoint_issues(context, token):
    _install_token_endpoint(
        context,
        lambda request: httpx.Response(200, json={"access_token": token, "expires_in": 3600}),
    )


@given("the token endpoint answers with status {status:d}")
def step_token_endpoint_status(context, status):
    _install_token_endpoint(context, lambda request: httpx.Response(status, text="error"))


@when('the gateway builds the authorization header with static token "{token}"')
def step_build_header_with_static(context, token):
    context.header = context.loop.run_until_complete(auth.get_authorization_header(token))


@when("the gateway builds the authorization header without static token")
def step_build_header_without_static(context):
    context.header = context.loop.run_until_complete(auth.get_authorization_header())


@when("the gateway builds the authorization header twice")
def step_build_header_twice(context):
    context.loop.run_until_complete(auth.get_authorization_header())
    context.header = context.loop.run_until_complete(auth.get_authorization_header())


@then('the authorization header should be "{value}"')
def step_header_equals(context, value):
    assert context.header == value, f"Expected {value!r}, got {context.header!r}"


@then("there should be no authorization header")
def step_no_header(context):
    assert context.header is None, f"Expected no header, got {context.header!r}"


@then("the token endpoint should have been called once")
def step_token_endpoint_called_once(context):
    count = len(context.token_requests)
    assert count == 1, f"Expected 1 token request, got {count}"
    body = context.token_requests[0].content.decode()
    assert "grant_type=client_credentials" in body, body
