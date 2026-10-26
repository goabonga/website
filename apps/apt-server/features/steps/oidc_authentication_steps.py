# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the OIDC authentication feature (auth service faked in-process)."""

import jwt
from apt_server.auth.introspection import TokenRevokedError, introspection_client
from apt_server.auth.userinfo import userinfo_client
from apt_server.config import settings
from behave import given


@given("the auth service is configured")
def auth_configured(context):
    context.patch(settings, "oauth2_issuer", "https://issuer.example")
    context.patch(settings, "oauth2_client_id", "apt-client")
    context.patch(settings, "oauth2_client_secret", "apt-secret")
    context.known_tokens = {}
    context.revoked_tokens = set()
    context.profile = {}

    async def validate(token):
        if token in context.revoked_tokens:
            raise TokenRevokedError("revoked")
        if token not in context.known_tokens:
            raise jwt.InvalidTokenError("unknown token")
        return context.known_tokens[token]

    async def userinfo(token):
        return context.profile

    context.patch(introspection_client, "validate_token_with_introspection", validate)
    context.patch(introspection_client, "validate_opaque_token", validate)
    context.patch(userinfo_client, "get_userinfo", userinfo)


@given('the auth service accepts token "{token}" for user "{user}" with scopes "{scopes}"')
def accept_token(context, token, user, scopes):
    context.known_tokens[token] = {"sub": user, "client_id": user, "scope": scopes}


@given('the auth service has revoked token "{token}"')
def revoke_token(context, token):
    context.revoked_tokens.add(token)


@given('the profile of the token owner has email "{email}"')
def set_profile(context, email):
    context.profile = {"email": email, "name": "Test User"}
