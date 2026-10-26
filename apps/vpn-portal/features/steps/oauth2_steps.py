# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for oauth2.feature.

The protected application uses the real ``require_scopes`` dependency; only the
collaborators that would reach the network (JWKS, introspection, token exchange)
are replaced.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from behave import given, then, when
from fastapi import Depends, FastAPI
from vpn_portal.auth import AuthContext, require_scopes
from vpn_portal.auth.introspection import TokenRevokedError
from vpn_portal.auth.models import User
from vpn_portal.auth.token_exchange import TokenExchangeError

JWT = "header.payload.signature"
OPAQUE = "opaque-personal-access-token"


def _claims(scope):
    return {"sub": str(uuid4()), "email": "user@example.com", "scope": scope}


def _patch(context, target):
    patcher = patch(target)
    mock = patcher.start()
    context.add_cleanup(patcher.stop)
    return mock


@given('a protected application with a route requiring the "{scope}" scope')
def step_protected_app(context, scope):
    app = FastAPI()

    @app.get("/protected")
    async def protected(auth: AuthContext = Depends(require_scopes(scope))):
        return {"user_id": auth.user_id, "scopes": auth.scopes}

    context.app = app
    context.jwks = _patch(context, "vpn_portal.auth.dependencies.jwks_manager")
    context.introspection = _patch(context, "vpn_portal.auth.dependencies.introspection_client")
    context.exchange = _patch(context, "vpn_portal.auth.dependencies.token_exchange_client")
    context.introspection.validate_token_with_introspection = AsyncMock()
    context.introspection.validate_opaque_token = AsyncMock()
    context.exchange.validate_token_scopes = AsyncMock()
    context.exchange.is_configured = False


@given("OAuth2 is configured")
def step_oauth2_configured(context):
    context.jwks.is_configured = True


@given("OAuth2 is not configured")
def step_oauth2_not_configured(context):
    context.jwks.is_configured = False


def _bearer(context, token):
    context.headers["Authorization"] = f"Bearer {token}"


@given('I present a JWT granting "{scope}"')
def step_jwt_granting(context, scope):
    context.introspection.validate_token_with_introspection.return_value = _claims(scope)
    _bearer(context, JWT)


@given("I present a revoked JWT")
def step_revoked_jwt(context):
    context.introspection.validate_token_with_introspection.side_effect = TokenRevokedError("x")
    _bearer(context, JWT)


@given("I present a JWT with an invalid signature")
def step_invalid_jwt(context):
    context.introspection.validate_token_with_introspection.side_effect = ValueError("bad")
    _bearer(context, JWT)


@given('I present an opaque token granting "{scope}"')
def step_opaque_token(context, scope):
    context.introspection.validate_opaque_token.return_value = _claims(scope)
    _bearer(context, OPAQUE)


@given('token exchange is configured and grants "{scope}"')
def step_exchange_grants(context, scope):
    context.exchange.is_configured = True
    context.exchange.validate_token_scopes.return_value = {
        "scope": scope,
        "claims": _claims("openid"),
    }


@given("token exchange is configured and refuses the scope")
def step_exchange_refuses(context):
    context.exchange.is_configured = True
    context.exchange.validate_token_scopes.side_effect = TokenExchangeError(
        "insufficient_scope: not granted", error_code="insufficient_scope"
    )


@given('a client_credentials claim set for client "{client_id}" with scope "{scope}"')
def step_machine_claims(context, client_id, scope):
    context.claims = {"sub": client_id, "client_id": client_id, "scope": scope}


@given('a user claim set with a UUID subject and scope "{scope}"')
def step_user_claims(context, scope):
    context.claims = {"sub": str(uuid4()), "email": "user@example.com", "scope": scope}


@when("the user is built from the claims")
def step_build_user(context):
    context.user = User.from_jwt_claims(context.claims)


@then("the user should be a machine client")
def step_is_machine(context):
    assert context.user.is_machine_client is True


@then("the user should not be a machine client")
def step_is_not_machine(context):
    assert context.user.is_machine_client is False


@then('the user should have the scope "{scope}"')
def step_has_scope(context, scope):
    assert context.user.has_scope(scope)
