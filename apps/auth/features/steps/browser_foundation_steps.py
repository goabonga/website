# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of the application foundation."""

from behave import given, then, when
from e2e_support import steps  # noqa: F401  (registers the generic browser steps)


@given("the browser records the requests it makes")
def step_record_requests(context):
    context.requested = []
    context.page.on("request", lambda request: context.requested.append(request.url))


@then("every request of the browser went to the application")
def step_requests_stayed_home(context):
    # Let the page finish loading the assets it asks for after the first paint.
    context.page.wait_for_load_state("networkidle")
    outside = [
        url for url in context.requested if not url.startswith((context.base_url, "data:", "blob:"))
    ]
    assert not outside, f"requests that left the application: {outside}"
    assert any(url.endswith("/static/swagger-ui-bundle.js") for url in context.requested)


@when('I fetch "{path}" with the browser')
def step_fetch(context, path):
    context.fetched = context.browser_context.request.get(f"{context.base_url}{path}")


@then("the browser received an image")
def step_received_image(context):
    assert context.fetched.status == 200, context.fetched.status
    assert context.fetched.headers["content-type"].startswith("image/"), context.fetched.headers
