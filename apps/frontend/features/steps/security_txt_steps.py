# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the security.txt feature."""

from behave import then


@then("the response text is")
def step_text_is(context) -> None:
    assert context.response.text == context.text, context.response.text


@then("the response text is empty")
def step_text_empty(context) -> None:
    assert context.response.text == ""
