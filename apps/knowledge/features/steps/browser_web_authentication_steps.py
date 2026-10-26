# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the web authentication feature in a browser.

The sign-in round trip goes through the fake OpenID provider; the sign-up, sign-in and
password pages talk to the authentication service stand-in of ``browser_auth``, whose
verification codes and reset links the steps read the way a user reads their mailbox.
"""

from urllib.parse import parse_qs, urlparse

import browser_stack
from behave import given, then, when
from playwright.sync_api import expect


def _provider(context):
    return context.stack.provider


def _service(context):
    return context.stack.auth_service


# --- the identity provider ------------------------------------------------------------


@then("the authorization request used the {method} code challenge method")
def step_challenge_method(context, method):
    query = parse_qs(urlparse(context.page.url).query)
    assert query["code_challenge_method"] == [method], query
    assert query["code_challenge"], query


@then('the identity provider issued tokens for the "{grant}" grant')
def step_issued_tokens(context, grant):
    grants = [r.form.get("grant_type") for r in _provider(context).requests_to("/oauth2/token")]
    assert grant in grants, grants


@when("the identity provider revokes every token and ends the sessions")
def step_revoke_tokens(context):
    _provider(context).revoke_tokens()
    _provider(context).end_sessions()


@given("I sign out")
def step_sign_out(context):
    context.page.goto("/auth/logout")
    _provider(context).end_sessions()


# --- registration ----------------------------------------------------------------------


@given('"{email}" has registered and awaits the verification code')
def step_registered(context, email):
    _service(context).preregister(email, browser_stack.PASSWORD, "ada", "Ada", "Lovelace")


@when('I enter the verification code sent to "{email}"')
def step_enter_code(context, email):
    type_code(context, _service(context).codes[email])


@when('I type the verification code "{code}"')
def step_type_code(context, code):
    type_code(context, code)


def type_code(context, code):
    context.page.locator("input.code-input").first.click()
    context.page.keyboard.type(code)
    expect(context.page.locator("#verify-btn")).to_be_enabled()
    context.page.locator("#verify-btn").click()


@then("no verification code was sent")
def step_no_code(context):
    assert not _service(context).codes, _service(context).codes


@when('I fill "{name}" with the password of the users')
def step_fill_password(context, name):
    context.page.get_by_label(name, exact=True).fill(browser_stack.PASSWORD)


# --- passwords --------------------------------------------------------------------------


@when('I open the password reset link sent to "{email}"')
def step_reset_link(context, email):
    token = next(t for t, owner in _service(context).reset_tokens.items() if owner == email)
    context.page.goto(f"/auth/reset-password?token={token}")


# --- account ------------------------------------------------------------------------------


@then('the authentication service holds the nickname "{nickname}" for "{email}"')
def step_nickname(context, nickname, email):
    user = _provider(context).user_by_email(email)
    assert _service(context).profiles[user.id]["nickname"] == nickname


# --- native dialogs -----------------------------------------------------------------------


@given("the browser records the alerts it shows")
def step_record_alerts(context):
    context.alerts = []
    context.page.on(
        "dialog", lambda dialog: (context.alerts.append(dialog.message), dialog.dismiss())
    )


@then('the browser should have shown the alert "{message}"')
def step_alert_shown(context, message):
    expect(context.page).to_have_url(context.page.url)  # let pending handlers run
    assert message in context.alerts, context.alerts
