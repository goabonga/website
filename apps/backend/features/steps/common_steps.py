# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Common step definitions for HTTP request and response handling."""

import json

from behave import then, when


@when('I send a GET request to "{path}"')
def step_send_get_request(context, path):
    context.response = context.client.get(path)


@then("the response status code should be {status_code:d}")
def step_check_status_code(context, status_code):
    assert context.response.status_code == status_code, (
        f"Expected {status_code}, got {context.response.status_code}. "
        f"Body: {context.response.text[:500]}"
    )


@then('the response JSON should contain "{key}" with value "{value}"')
def step_check_json_key_value(context, key, value):
    data = context.response.json()
    assert key in data, f"Key '{key}' not found in response: {data}"
    assert str(data[key]) == value, f"Expected '{value}', got '{data[key]}'"


@then('the response JSON should have exactly the keys "{keys}"')
def step_check_json_exact_keys(context, keys):
    expected_keys = {k.strip() for k in keys.split(",")}
    actual_keys = set(context.response.json().keys())
    assert actual_keys == expected_keys, f"Expected keys {expected_keys}, got {actual_keys}"


@then('the response content type should be "{content_type}"')
def step_check_content_type(context, content_type):
    actual = context.response.headers.get("content-type", "")
    assert content_type in actual, f"Expected content type '{content_type}', got '{actual}'"


@then('the response body should contain "{text}"')
def step_check_body_contains(context, text):
    assert text in context.response.text, (
        f"Expected body to contain '{text}', got: {context.response.text[:500]}"
    )


@then("the response body should be empty")
def step_check_body_empty(context):
    body = context.response.text.strip()
    assert body == "", f"Expected empty body, got: {body[:200]}"


@then('the response JSON "{key}" should not be null')
def step_check_json_not_null(context, key):
    data = context.response.json()
    assert key in data, f"Key '{key}' not in response"
    assert data[key] is not None, f"Expected '{key}' to not be null"


@then('the response JSON "{key}" should be null')
def step_check_json_null(context, key):
    data = context.response.json()
    assert key in data, f"Key '{key}' not in response"
    assert data[key] is None, f"Expected '{key}' to be null, got {data[key]}"


@then('the response header "{header}" should be "{value}"')
def step_check_response_header(context, header, value):
    actual = context.response.headers.get(header)
    assert actual == value, f"Expected header '{header}' to be '{value}', got '{actual}'"


@when('I send a POST request to "{path}" with body:')
def step_send_post_request_with_body(context, path):
    context.response = context.client.post(path, json=json.loads(context.text))


@then('the response content type should contain "{content_type}"')
def step_check_content_type_contains(context, content_type):
    actual = context.response.headers.get("content-type", "")
    assert content_type in actual, (
        f"Expected content type to contain '{content_type}', got '{actual}'"
    )


@then('the response JSON "{key}" should be an empty list')
def step_check_json_empty_list(context, key):
    data = context.response.json()
    assert key in data, f"Key '{key}' not in response"
    assert data[key] == [], f"Expected empty list, got {data[key]}"


@then('the response JSON "{key}" should have {count:d} items')
def step_check_json_list_count(context, key, count):
    data = context.response.json()
    assert key in data, f"Key '{key}' not in response"
    assert len(data[key]) == count, f"Expected {count} items, got {len(data[key])}"


@then('the response JSON at "{path}" should be "{value}"')
def step_check_json_path(context, path, value):
    """Navigate a dotted path like 'messages[0].role' into the JSON."""
    current = context.response.json()
    for part in path.replace("]", "").replace("[", ".").split("."):
        current = current[int(part)] if part.isdigit() else current[part]
    assert str(current) == value, f"At path '{path}': expected '{value}', got '{current}'"


@then('the response should set a "{cookie_name}" cookie')
def step_check_cookie_set(context, cookie_name):
    cookie_header = context.response.headers.get("set-cookie", "")
    assert cookie_name in cookie_header, (
        f"Expected '{cookie_name}' cookie to be set. Set-Cookie header: '{cookie_header}'"
    )
