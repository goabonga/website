# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the security.txt feature."""

from analytics.config import settings
from behave import given, then

FIELDS = [
    "contact",
    "expires",
    "encryption",
    "acknowledgments",
    "preferred_languages",
    "canonical",
    "policy",
    "hiring",
    "csaf",
]


def _set_field(context, field, value):
    attribute = f"security_{field}"
    previous = getattr(settings, attribute)
    setattr(settings, attribute, value)
    context.add_cleanup(setattr, settings, attribute, previous)


@given("no security.txt field is configured")
def step_no_fields(context):
    for field in FIELDS:
        _set_field(context, field, "")


@given('the security.txt field "{field}" is "{value}"')
def step_set_field(context, field, value):
    assert field in FIELDS, f"Unknown security.txt field: {field}"
    _set_field(context, field, value)


@then("the response body should be empty")
def step_body_empty(context):
    assert context.response.text == "", f"Expected empty body, got: {context.response.text!r}"
