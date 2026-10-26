# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps checking what the hooks put on the behave context."""

from behave import then, when


@when('I open "{path}" with the raw page')
def open_with_page(context, path):
    context.page.goto(path)


@then('the raw page title is "{title}"')
def raw_title(context, title):
    assert context.page.title() == title, context.page.title()


@then("the context holds a page, a browser context and the base URL")
def context_is_populated(context):
    assert context.page.context is context.browser_context
    assert context.base_url.startswith("http://127.0.0.1:")


@then("the context holds no page")
def context_has_no_page(context):
    assert not hasattr(context, "page")
    assert not hasattr(context, "browser_context")


@then("the scenario fails on purpose")
def fail_on_purpose(context):
    raise AssertionError("failing on purpose")


@then("the cookie jar is empty")
def cookie_jar_empty(context):
    assert context.browser_context.cookies() == []


@when("I visit the page that sets a cookie")
def set_cookie(context):
    context.page.goto("/set-cookie")
    assert context.browser_context.cookies()
