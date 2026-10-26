# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the single page application serving browser scenarios."""

from behave import then
from e2e_support.steps import current_page


@then('the web client configuration "{path}" is "{value}"')
def web_client_configuration(context, path, value):
    """Compare a value of ``window.APP_CONFIG`` (lists are joined with commas)."""
    actual = current_page(context).evaluate(
        "path => path.split('.').reduce((value, key) => value[key], window.APP_CONFIG)", path
    )
    if isinstance(actual, list):
        actual = ",".join(actual)
    assert actual == value, f"{path} is {actual!r}, expected {value!r}"
