# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Common step definitions for HTTP request and response handling."""

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
