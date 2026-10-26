# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared step definitions for BDD tests.

Provides reusable Given/When/Then steps for HTTP requests and response assertions.
"""

import json

from behave import given, then, when

# -- Helper ------------------------------------------------------------------─


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


# -- Given Steps --------------------------------------------------------------


@given("I am authenticated")
def step_authenticated(context):
    """Use the default authenticated client (already set up in environment)."""
    context.use_auth = True


@given("I am not authenticated")
def step_not_authenticated(context):
    """Use the anonymous client for this scenario."""
    context.use_auth = False


# -- When Steps (HTTP requests) ----------------------------------------------─


def _get_client(context):
    """Return the appropriate client based on auth state."""
    auth = getattr(context, "use_auth", True)
    if auth:
        return context.client
    return context.anon_client


@when('I send a GET to "{path}"')
def step_send_get(context, path):
    """Send a GET request to the given path."""
    path = _resolve_path(context, path)
    client = _get_client(context)
    context.response = _run(context, client.get(path))


@when('I send a POST to "{path}" with')
def step_send_post_with_body(context, path):
    """Send a POST request with JSON body from the step text."""
    path = _resolve_path(context, path)
    resolved_text = _resolve_path(context, context.text)
    body = json.loads(resolved_text)
    client = _get_client(context)
    context.response = _run(context, client.post(path, json=body))


@when('I send a POST to "{path}"')
def step_send_post_no_body(context, path):
    """Send a POST request without body."""
    path = _resolve_path(context, path)
    client = _get_client(context)
    context.response = _run(context, client.post(path))


@when('I send a PATCH to "{path}" with')
def step_send_patch_with_body(context, path):
    """Send a PATCH request with JSON body from the step text."""
    path = _resolve_path(context, path)
    resolved_text = _resolve_path(context, context.text)
    body = json.loads(resolved_text)
    client = _get_client(context)
    context.response = _run(context, client.patch(path, json=body))


@when('I send a DELETE to "{path}"')
def step_send_delete(context, path):
    """Send a DELETE request."""
    path = _resolve_path(context, path)
    client = _get_client(context)
    context.response = _run(context, client.delete(path))


@when('I send a raw POST to "{path}" with body "{body}" and header "{header_name}: {header_value}"')
def step_send_raw_post(context, path, body, header_name, header_value):
    """Send a raw POST with string body and custom header."""
    path = _resolve_path(context, path)
    client = _get_client(context)
    context.response = _run(
        context,
        client.post(path, content=body.encode(), headers={header_name: header_value}),
    )


# -- Then Steps (Response assertions) ----------------------------------------


@then("the response status should be {status_code:d}")
def step_check_status(context, status_code):
    assert context.response is not None, "No response captured"
    assert context.response.status_code == status_code, (
        f"Expected {status_code}, got {context.response.status_code}. "
        f"Body: {context.response.text[:500]}"
    )


@then('the response JSON should contain "{key}"')
def step_check_json_has_key(context, key):
    data = context.response.json()
    assert key in data, f"Key '{key}' not found in response: {list(data.keys())}"


@then('the response JSON "{key}" should be "{value}"')
def step_check_json_value_str(context, key, value):
    data = context.response.json()
    assert str(data.get(key)) == value, f"Expected {key}='{value}', got '{data.get(key)}'"


@then('the response JSON "{key}" should be true')
def step_check_json_value_true(context, key):
    data = context.response.json()
    assert data.get(key) is True, f"Expected {key}=True, got {data.get(key)}"


@then('the response JSON "{key}" should be false')
def step_check_json_value_false(context, key):
    data = context.response.json()
    assert data.get(key) is False, f"Expected {key}=False, got {data.get(key)}"


@then("the response JSON should be a list of {count:d} items")
def step_check_json_list_count(context, count):
    data = context.response.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    assert len(data) == count, f"Expected {count} items, got {len(data)}"


@then("the response JSON should be a non-empty list")
def step_check_json_list_nonempty(context):
    data = context.response.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    assert len(data) > 0, "Expected non-empty list"


@then("the response JSON should be an empty list")
def step_check_json_list_empty(context):
    data = context.response.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    assert len(data) == 0, f"Expected empty list, got {len(data)} items"


@then('I store the response "{field}" as "{alias}"')
def step_store_response_field(context, field, alias):
    """Store a response field for use in later steps."""
    data = context.response.json()
    assert field in data, f"Field '{field}' not in response"
    context.created_ids[alias] = str(data[field])


# -- Path Resolution ----------------------------------------------------------


def _resolve_path(context, path):
    """Replace {alias} placeholders in paths with stored IDs."""
    for alias, value in getattr(context, "created_ids", {}).items():
        path = path.replace("{" + alias + "}", value)
    return path
