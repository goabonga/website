# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions shared across features."""

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from behave import given, then, when
from reachy_mini_api.auth import jwks_manager


@when('I send a GET request to "{path}"')
def step_send_get_request(context, path):
    """Send a GET request to the ASGI application."""
    context.send_request("GET", path)


@then("the response status code should be {status_code:d}")
def step_check_status_code(context, status_code):
    """Check the response status code."""
    actual = context.response.status_code
    assert actual == status_code, f"Expected {status_code}, got {actual}: {context.response.text}"


@then('the response JSON field "{field}" should be "{value}"')
def step_check_json_field(context, field, value):
    """Check a top-level string field of the JSON response."""
    actual = json.loads(context.response.text)[field]
    assert str(actual) == value, f"Expected {value!r}, got {actual!r}"


@given('I am authenticated with scope "{scope}"')
def step_authenticated_with_scope(context, scope):
    """Fake the JWT validation so that the token carries exactly the given scope."""
    claims = {"sub": str(uuid4()), "scope": scope, "client_id": "behave-client"}
    patcher = patch.object(jwks_manager, "validate_token", AsyncMock(return_value=claims))
    patcher.start()
    context.patchers.append(patcher)
    context.auth_headers = {"Authorization": "Bearer behave.test.token"}


@when('I request "{method} {path}"')
def step_request(context, method, path):
    """Send a request, with the bearer token when the scenario is authenticated."""
    context.send_request(method, path)


def response_json(context):
    """Return the decoded JSON body."""
    return json.loads(context.response.text)


@then('the response should contain "{field}"')
def step_response_contains_field(context, field):
    """Check that a top-level field is present."""
    assert field in response_json(context), f"{field!r} not in {context.response.text}"


@then('the response field "{field}" should be {value:d}')
def step_field_is_number(context, field, value):
    """Check an integer field."""
    assert response_json(context)[field] == value


@then('the response field "{field}" should be a list')
def step_field_is_list(context, field):
    """Check that a field is a list."""
    assert isinstance(response_json(context)[field], list)


@then('the response field "{field}" should have {count:d} items')
def step_field_has_items(context, field, count):
    """Check the length of a list field."""
    assert len(response_json(context)[field]) == count


@then('each item in "{field}" should contain "{key}"')
def step_items_contain(context, field, key):
    """Check that every item of a list field has the key."""
    items = response_json(context)[field]
    assert items and all(key in item for item in items), f"{key!r} missing in {items}"
