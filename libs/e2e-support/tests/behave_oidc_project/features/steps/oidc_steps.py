# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Generic browser steps, plus the steps that talk to the fake provider."""

from behave import then, when
from e2e_support import steps  # noqa: F401


def provider_of(context):
    return context.e2e.servers["provider"].app


@when("the provider ends every session")
def end_sessions(context):
    provider_of(context).end_sessions()
    provider_of(context).revoke_tokens()


@then('the provider received a token request for the "{grant}" grant')
def token_request_received(context, grant):
    grants = [r.form["grant_type"] for r in provider_of(context).requests_to("/oauth2/token")]
    assert grant in grants, f"token requests were for {grants}"


@then("the provider never showed a login page")
def no_login_page(context):
    pages = [
        r
        for r in provider_of(context).requests_to("/oauth2/authorize")
        if r.status == 200 and b"Sign in" in r.response_body
    ]
    assert not pages, "the login page was served"
