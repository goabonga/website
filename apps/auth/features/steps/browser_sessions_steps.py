# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of sessions and logout."""

import time

from auth.config import settings
from behave import given, then, when

DAY = 24 * 3600


def cookie(context, name):
    """The cookie called ``name`` of the browser context, or ``None``."""
    return next((c for c in context.browser_context.cookies() if c["name"] == name), None)


@given("the browser holds the cookie of the session")
def step_hold_cookie(context):
    """Hand the opened session to the browser the way a sign-in would."""
    context.browser_context.add_cookies(
        [
            {
                "name": settings.session_cookie_name,
                "value": context.session_token,
                "url": context.base_url,
                "expires": time.time() + settings.session_expiry_days * DAY,
                "httpOnly": True,
                "secure": settings.session_cookie_secure,
                "sameSite": "Lax",
            }
        ]
    )


@given("the browser holds no cookie")
def step_no_cookie(context):
    context.browser_context.clear_cookies()


@when('the page posts to "{path}" without leaving the page')
def step_post_in_page(context, path):
    context.fetch_status = context.page.evaluate(
        "async (path) => (await fetch(path, {method: 'POST', credentials: 'same-origin'})).status",
        path,
    )


@when('the page submits a form posting to "{path}"')
def step_submit_form(context, path):
    """A logout button as a page of the application renders it (none exists on this page)."""
    context.page.evaluate(
        """(path) => {
            const form = document.createElement('form');
            form.method = 'post';
            form.action = path;
            const button = document.createElement('button');
            button.textContent = 'Submit form';
            form.appendChild(button);
            document.body.appendChild(form);
        }""",
        path,
    )
    context.page.get_by_role("button", name="Submit form").click()


@then("the page request was answered with status {status:d}")
def step_fetch_status(context, status):
    assert context.fetch_status == status, context.fetch_status


@then("the session cookie of the browser is HttpOnly, Secure and SameSite Lax")
def step_cookie_flags(context):
    found = cookie(context, settings.session_cookie_name)
    assert found is not None, "the browser holds no session cookie"
    assert found["httpOnly"] is True, found
    assert found["secure"] is settings.session_cookie_secure, found
    assert found["sameSite"] == "Lax", found


@then("the session cookie expires in about {days:d} days")
def step_cookie_expiry(context, days):
    found = cookie(context, settings.session_cookie_name)
    remaining = found["expires"] - time.time()
    assert days * DAY - 600 < remaining <= days * DAY + 60, remaining / DAY


@then("the session cookie expires in less than {minutes:d} minutes")
def step_cookie_short(context, minutes):
    found = cookie(context, settings.session_cookie_name)
    assert found["expires"] - time.time() < minutes * 60, found


@then("the scripts of the page cannot read the session cookie")
def step_cookie_hidden(context):
    visible = context.page.evaluate("document.cookie")
    assert settings.session_cookie_name not in visible, visible


@then("the browser no longer holds the session cookie")
def step_cookie_gone(context):
    assert cookie(context, settings.session_cookie_name) is None
