# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the OAuth2 authentication feature."""

from behave import given
from custom_domain.auth import AuthContext, require_scopes
from custom_domain.auth.introspection import TokenRevokedError
from environment import authenticate
from fastapi import Depends, FastAPI


@given('a protected endpoint requiring the scope "{scope}"')
def step_protected_endpoint(context, scope):
    probe = FastAPI()

    @probe.get("/protected")
    async def protected(auth: AuthContext = Depends(require_scopes(scope))):
        return {
            "user_id": auth.user_id,
            "client_id": auth.user.client_id,
            "scopes": auth.scopes,
            "is_machine_client": auth.user.is_machine_client,
        }

    context.app = probe


@given('I am authenticated as machine client "{client_id}" with scopes "{scopes}"')
def step_authenticated_machine(context, client_id, scopes):
    authenticate(context, scopes.split(), client_id=client_id, subject=client_id)


@given("the auth server reports every token as revoked")
def step_revoked(context):
    authenticate(context, ["custom-domain:read"], error=TokenRevokedError("revoked"))
