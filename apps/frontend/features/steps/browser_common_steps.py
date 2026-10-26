# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by the browser scenarios: serve the application, visit a path, inspect it."""

import re

import browser_support
from behave import given, step, then
from e2e_support import steps  # noqa: F401
from e2e_support.steps import current_page


@given("the web client is built")
def web_client_built(context):
    try:
        context.overrides["static_dir"] = str(browser_support.client_build())
    except browser_support.ClientBuildUnavailable as exc:
        context.scenario.skip(f"the web client cannot be built: {exc}")


@step("the application is running")
def application_running(context):
    """Serve the application with the settings given so far, and note what the page loads."""
    context.base_url = browser_support.serve(context)
    context.loaded = []
    current_page(context).on("response", lambda response: context.loaded.append(response))


@step('I visit "{path}"')
def visit(context, path):
    context.visit = current_page(context).goto(f"{context.base_url}{path}")


@then("the page answers {status:d}")
def page_answers(context, status):
    assert context.visit.status == status, f"expected {status}, got {context.visit.status}"


@then('the content type of the page is "{content_type}"')
def page_content_type(context, content_type):
    actual = context.visit.header_value("content-type")
    assert actual == content_type, f"the content type is {actual}"


@then('the browser loaded "{path}" as "{content_type}"')
def browser_loaded(context, path, content_type):
    found = [r for r in context.loaded if r.url == f"{context.base_url}{path}"]
    assert found, f"the browser did not load {path}: {[r.url for r in context.loaded]}"
    actual = found[0].header_value("content-type") or ""
    assert found[0].status == 200 and content_type in actual, f"{found[0].status} {actual}"


@then('the browser reported an error matching "{pattern}"')
def browser_reported(context, pattern):
    errors = [str(entry) for entry in context.e2e.scenario.diagnostics.errors]
    assert any(re.search(pattern, error) for error in errors), f"errors were {errors}"
