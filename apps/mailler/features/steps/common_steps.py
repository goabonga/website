# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared step definitions: HTTP requests and response assertions."""

import json

from behave import then, when


def _run(context, coro):
    """Run an async coroutine from a synchronous behave step."""
    return context.loop.run_until_complete(coro)


def _resolve(context, value):
    """Replace {alias} placeholders with identifiers stored by earlier steps."""
    for alias, stored in getattr(context, "created_ids", {}).items():
        value = value.replace("{" + alias + "}", stored)
    return value


def _get_client(context):
    """Return the HTTP client used by the current scenario."""
    return context.client


# -- When: HTTP requests ------------------------------------------------------


@when('I send a GET to "{path}"')
def step_send_get(context, path):
    context.response = _run(context, _get_client(context).get(_resolve(context, path)))


@when('I send a POST to "{path}" with')
def step_send_post_with_body(context, path):
    body = json.loads(_resolve(context, context.text))
    context.response = _run(context, _get_client(context).post(_resolve(context, path), json=body))


@when('I send a POST to "{path}"')
def step_send_post_no_body(context, path):
    context.response = _run(context, _get_client(context).post(_resolve(context, path)))


@when('I send a PATCH to "{path}" with')
def step_send_patch_with_body(context, path):
    body = json.loads(_resolve(context, context.text))
    context.response = _run(context, _get_client(context).patch(_resolve(context, path), json=body))


@when('I send a PUT to "{path}" with')
def step_send_put_with_body(context, path):
    body = json.loads(_resolve(context, context.text))
    context.response = _run(context, _get_client(context).put(_resolve(context, path), json=body))


@when('I send a DELETE to "{path}"')
def step_send_delete(context, path):
    context.response = _run(context, _get_client(context).delete(_resolve(context, path)))


@when('I send a DELETE to "{path}" with')
def step_send_delete_with_body(context, path):
    body = json.loads(_resolve(context, context.text))
    context.response = _run(
        context,
        _get_client(context).request("DELETE", _resolve(context, path), json=body),
    )


# -- Then: response assertions ------------------------------------------------


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
    assert context.response.json().get(key) is True


@then('the response JSON "{key}" should be false')
def step_check_json_value_false(context, key):
    assert context.response.json().get(key) is False


@then("the response JSON should be a list of {count:d} items")
def step_check_json_list_count(context, count):
    data = context.response.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    assert len(data) == count, f"Expected {count} items, got {len(data)}"


@then("the response JSON should be a non-empty list")
def step_check_json_list_nonempty(context):
    data = context.response.json()
    assert isinstance(data, list) and len(data) > 0, "Expected non-empty list"


@then("the response JSON should be an empty list")
def step_check_json_list_empty(context):
    data = context.response.json()
    assert isinstance(data, list) and len(data) == 0, f"Expected empty list, got {data}"


@then('the response should contain "{text}"')
def step_check_response_contains(context, text):
    assert text in context.response.text, f"Expected '{text}' in: {context.response.text[:500]}"


@then('I store the response "{field}" as "{alias}"')
def step_store_response_field(context, field, alias):
    data = context.response.json()
    assert field in data, f"Field '{field}' not in response"
    context.created_ids[alias] = str(data[field])


@then('the response should not contain "{text}"')
def step_check_response_not_contains(context, text):
    assert text not in context.response.text, f"Unexpected '{text}' in: {context.response.text}"


@then('the response header "{name}" should be "{value}"')
def step_check_header(context, name, value):
    assert context.response.headers.get(name) == value, dict(context.response.headers)


@when('I send a CORS preflight to "{path}" from "{origin}"')
def step_cors_preflight(context, path, origin):
    context.response = _run(
        context,
        _get_client(context).options(
            _resolve(context, path),
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        ),
    )


@then('the response JSON "{key}" should have {count:d} entries')
def step_check_json_entries(context, key, count):
    value = context.response.json()[key]
    assert len(value) == count, f"Expected {count} entries in {key}, got {len(value)}"


@then('the response JSON "{key}" should include an entry with "{field}" equal to "{value}"')
def step_check_json_entry_includes(context, key, field, value):
    entries = context.response.json()[key]
    assert any(str(entry.get(field)) == value for entry in entries), entries


@then('the response JSON "{key}" should not include an entry with "{field}" equal to "{value}"')
def step_check_json_entry_excludes(context, key, field, value):
    entries = context.response.json()[key]
    assert not any(str(entry.get(field)) == value for entry in entries), entries


def _lookup(data, path):
    """Follow a dotted path through dictionaries."""
    for part in path.split("."):
        data = data[part]
    return data


@then('the response JSON path "{path}" should be "{value}"')
def step_check_json_path(context, path, value):
    actual = _lookup(context.response.json(), path)
    assert str(actual) == value, f"Expected {path}='{value}', got '{actual}'"


@then('the response JSON "{key}" should not have key "{name}"')
def step_check_json_missing_key(context, key, name):
    assert name not in context.response.json()[key], context.response.json()[key]
