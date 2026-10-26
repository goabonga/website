# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the APT client endpoints feature."""

import base64

import jwt
from apt_server.auth.introspection import introspection_client
from apt_server.config import settings
from behave import given, then, when


@given('the auth service knows access token "{token}" for user "{user}"')
def known_access_token(context, token, user):
    if not hasattr(context, "access_tokens"):
        context.access_tokens = {}
        context.patch(settings, "oauth2_issuer", "https://issuer.example")
        context.patch(settings, "apt_gpg_key_id", "")

        async def validate(presented):
            if presented not in context.access_tokens:
                raise jwt.InvalidTokenError("unknown token")
            return context.access_tokens[presented]

        context.patch(introspection_client, "validate_opaque_token", validate)
    context.access_tokens[token] = {"sub": user, "scope": "apt:read"}


@when('I request "{path}" with access token "{token}"')
def request_with_access_token(context, path, token):
    credentials = base64.b64encode(f"apt:{token}".encode()).decode()
    context.response = context.client.get(path, headers={"Authorization": f"Basic {credentials}"})


@then('the response body contains "{text}"')
def body_contains(context, text):
    assert text in context.response.text, context.response.text


@then('the response body does not contain "{text}"')
def body_does_not_contain(context, text):
    assert text not in context.response.text


@then('the response header "{name}" starts with "{prefix}"')
def header_starts_with(context, name, prefix):
    assert context.response.headers[name].startswith(prefix), context.response.headers
