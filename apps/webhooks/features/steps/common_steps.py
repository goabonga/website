# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions shared across features."""

import json

import httpx
from behave import given, then, when
from httpx import ASGITransport, AsyncClient
from webhooks.config import settings


def _override_setting(context, name, value):
    """Override a setting until the end of the scenario."""
    context.setting_backup.setdefault(name, getattr(settings, name))
    setattr(settings, name, value)


def _post(context, path, content, headers):
    """Send a POST request to the ASGI application."""
    context.request_body = content

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.post(path, content=content, headers=headers)

    context.response = context.loop.run_until_complete(make_request())


@when('I send a GET request to "{path}"')
def step_send_get_request(context, path):
    """Send a GET request to the ASGI application."""

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.get(path)

    context.response = context.loop.run_until_complete(make_request())


@then("the response status code should be {status_code:d}")
def step_check_status_code(context, status_code):
    """Check the response status code."""
    actual = context.response.status_code
    assert actual == status_code, f"Expected {status_code}, got {actual}: {context.response.text}"


@then("the response should be valid JSON")
def step_response_is_json(context):
    """Check that the response body is valid JSON."""
    try:
        context.response_json = context.response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e


@then('the response JSON key "{key}" should equal "{value}"')
def step_json_key_equals(context, key, value):
    """Check that a JSON key has a specific value."""
    payload = context.response.json()
    actual = str(payload.get(key))
    assert actual == value, f"Expected {key}='{value}', got '{actual}'"


@when('I send a POST request to "{path}" with body')
def step_send_post_request_with_body(context, path):
    """Send a JSON POST request with the scenario docstring as body."""
    headers = {"Content-Type": "application/json", **context.custom_headers}
    _post(context, path, context.text.encode(), headers)


@when('I send a POST request to "{path}" with headers and body')
def step_send_post_with_headers_body(context, path):
    """Send a JSON POST request with the headers collected so far."""
    headers = {"Content-Type": "application/json", **context.custom_headers}
    _post(context, path, context.text.encode(), headers)


@when('I send an empty POST request to "{path}"')
def step_send_empty_post(context, path):
    """Send a POST request without a body."""
    _post(context, path, b"", {})


@given('the request has header "{name}" with value "{value}"')
def step_set_custom_header(context, name, value):
    """Set a custom header for the next request."""
    context.custom_headers[name] = value


@given('the {provider} internal API token is "{token}"')
def step_set_internal_api_token(context, provider, token):
    """Set the static internal API token of a provider."""
    _override_setting(context, f"{provider.lower()}_internal_api_token", token)


@given('the {provider} webhook secret is "{secret}"')
def step_set_webhook_secret(context, provider, secret):
    """Set the webhook secret of a provider."""
    _override_setting(context, f"{provider.lower()}_webhook_secret", secret)


@given("the internal API answers with status {status:d}")
def step_internal_api_status(context, status):
    """Make every mocked internal API answer with the given status."""
    for response in context.client_responses.values():
        response.status_code = status


@given("the internal API cannot be reached")
def step_internal_api_unreachable(context):
    """Make every mocked internal API refuse connections."""
    for client in context.clients.values():
        client.post.side_effect = httpx.ConnectError("connection refused")


def _called_clients(context):
    return [name for name, client in context.clients.items() if client.post.called]


@then("the internal API should have been called")
def step_internal_api_called(context):
    assert _called_clients(context), "Expected the internal API to be called"


@then("the internal API should not have been called")
def step_internal_api_not_called(context):
    called = _called_clients(context)
    assert not called, f"Expected the internal API not to be called, but {called} was"


def _last_call_headers(context):
    called = _called_clients(context)
    assert called, "Expected the internal API to be called"
    return context.clients[called[0]].post.call_args.kwargs.get("headers", {})


@then('the internal API should have received authorization "{value}"')
def step_internal_api_received_authorization(context, value):
    actual = _last_call_headers(context).get("Authorization", "")
    assert actual == value, f"Expected Authorization '{value}', got '{actual}'"


@then("the internal API should not have received authorization")
def step_internal_api_no_authorization(context):
    headers = _last_call_headers(context)
    assert "Authorization" not in headers, f"Unexpected Authorization: {headers['Authorization']}"


@then('the internal API should have received header "{name}" with value "{value}"')
def step_internal_api_received_header(context, name, value):
    actual = _last_call_headers(context).get(name)
    assert actual == value, f"Expected {name}='{value}', got '{actual}'"


@then('the internal API should have received path "{path}"')
def step_internal_api_received_path(context, path):
    called = _called_clients(context)
    assert called, "Expected the internal API to be called"
    actual = context.clients[called[0]].post.call_args.args[0]
    assert actual == path, f"Expected path '{path}', got '{actual}'"


@then("the internal API should have received the request body")
def step_internal_api_received_body(context):
    called = _called_clients(context)
    assert called, "Expected the internal API to be called"
    actual = context.clients[called[0]].post.call_args.kwargs["content"]
    assert actual == context.request_body, f"Unexpected forwarded body: {actual!r}"


@given("the {provider} internal API is not configured")
def step_internal_api_not_configured(context, provider):
    """Remove the socket and URL of a provider's internal API."""
    _override_setting(context, f"{provider.lower()}_internal_api_url", "")
    _override_setting(context, f"{provider.lower()}_internal_api_socket", "")
