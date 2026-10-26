# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by every feature file."""

import json

from behave import given, then, when
from environment import authenticate, http_request


@when('I send a {method} request to "{path}"')
def step_send_request(context, method, path):
    http_request(context, method, path)


@when('I send a {method} request to "{path}" with JSON')
def step_send_json_request(context, method, path):
    http_request(context, method, path, json=json.loads(context.text))


@given('I am authenticated as client "{client_id}" with scopes "{scopes}"')
def step_authenticated(context, client_id, scopes):
    authenticate(context, scopes.split(), client_id=client_id)


@given("I am not authenticated")
def step_not_authenticated(context):
    context.token = None


@then("the response status is {status:d}")
def step_response_status(context, status):
    assert context.response.status_code == status, context.response.text


@then('the JSON field "{field}" equals "{value}"')
def step_json_field_equals(context, field, value):
    assert str(context.response.json()[field]) == value


@then('the JSON field "{field}" has {count:d} items')
def step_json_field_items(context, field, count):
    assert len(context.response.json()[field]) == count, context.response.json()


@then('the JSON field "{field}" contains "{text}"')
def step_json_field_contains(context, field, text):
    assert text in str(context.response.json()[field]), context.response.json()


@then('the JSON field "{field}" is true')
def step_json_field_true(context, field):
    assert context.response.json()[field] is True


@then('the JSON field "{field}" is false')
def step_json_field_false(context, field):
    assert context.response.json()[field] is False


@then('the JSON field "{field}" is null')
def step_json_field_null(context, field):
    assert context.response.json()[field] is None
