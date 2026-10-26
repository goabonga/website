# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the web login sessions browser scenarios."""

import browser_support
from behave import step, then


def cookie(context, name):
    found = [c for c in context.browser_context.cookies() if c["name"] == name]
    return found[0] if found else None


@then('the browser holds the cookie "{name}"')
def holds_cookie(context, name):
    assert cookie(context, name) is not None, f"no cookie {name}"


@then('the browser does not hold the cookie "{name}"')
def does_not_hold_cookie(context, name):
    assert cookie(context, name) is None, f"cookie {name} is set"


@then('the cookie "{name}" is HTTP only and secure')
def cookie_flags(context, name):
    found = cookie(context, name)
    assert found["httpOnly"] and found["secure"], found


@step('the browser is given the cookie "{name}" with the value "{value}"')
def give_cookie(context, name, value):
    context.browser_context.add_cookies(
        [{"name": name, "value": value, "url": context.base_url, "secure": True}]
    )


@then('the provider received a token request for the "{grant}" grant')
def token_request_received(context, grant):
    provider = browser_support.provider_of(context)
    grants = [r.form["grant_type"] for r in provider.requests_to("/oauth2/token")]
    assert grant in grants, f"token requests were for {grants}"


@step("the provider revokes every token")
def provider_revokes(context):
    browser_support.provider_of(context).revoke_tokens()
