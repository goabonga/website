# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for authentication scenarios."""

from uuid import uuid4

from behave import given


def _register(context, token, scopes, **extra):
    """Register a token that validates to claims with the given scopes."""
    context.token_claims[token] = {
        "sub": str(uuid4()),
        "email": "bdd@example.com",
        "name": "BDD User",
        "scope": " ".join(scopes),
        "client_id": "bdd-client",
        **extra,
    }
    context.client.headers["Authorization"] = f"Bearer {token}"


@given('I am authenticated as client "{client}" with scopes "{scopes}"')
def step_authenticated_as_client(context, client, scopes):
    """Authenticate as a given client, so isolation between clients can be exercised."""
    _register(context, f"{client}.jwt.token", scopes.split(), client_id=client)


@given('I am authenticated without client identity with scopes "{scopes}"')
def step_authenticated_without_client(context, scopes):
    _register(context, "anonymous-client.jwt.token", scopes.split(), client_id=None)


@given('I am authenticated with only the authorized party "{azp}" and scopes "{scopes}"')
def step_authenticated_with_azp(context, azp, scopes):
    _register(context, f"{azp}.azp.jwt.token", scopes.split(), client_id=None, azp=azp)


@given("I am authenticated")
def step_authenticated(context):
    """Authenticate with the wildcard scope ``mailler:*``."""
    _register(context, "admin.jwt.token", ["mailler:*"])


@given('I am authenticated with scopes "{scopes}"')
def step_authenticated_with_scopes(context, scopes):
    _register(context, "scoped.jwt.token", scopes.split())


@given("I am authenticated as webhook service")
def step_authenticated_webhook(context):
    """Authenticate as a machine client holding only the webhooks scope."""
    _register(
        context,
        "webhook.jwt.token",
        ["mailler:webhooks"],
        sub="webhooks-api",
        client_id="webhooks-api",
    )


@given("I am authenticated with an opaque token")
def step_authenticated_opaque(context):
    _register(context, "opaque-personal-access-token", ["mailler:read"])


@given("I am authenticated with a revoked token")
def step_authenticated_revoked(context):
    _register(context, "revoked.jwt.token", ["mailler:*"])
    context.revoked_tokens.add("revoked.jwt.token")


@given("I am authenticated with an unknown token")
def step_authenticated_unknown(context):
    context.client.headers["Authorization"] = "Bearer unknown.jwt.token"


@given("I am not authenticated")
def step_not_authenticated(context):
    context.client.headers.pop("Authorization", None)


@given("the OAuth2 provider is not configured")
def step_oauth2_not_configured(context):
    context.jwks.is_configured = False
