# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the authentication feature: a protected application and an in-memory auth server."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from behave import given, then, when
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from team.auth import AuthContext, User, require_scopes
from team.auth.introspection import TokenRevokedError
from team.auth.token_exchange import TokenExchangeError


class FakeAuthServer:
    """What the introspection, JWKS and token exchange clients answer in a scenario."""

    def __init__(self) -> None:
        self.claims: dict | None = None
        self.revoked = False
        self.rejected = False
        self.opaque_validations = 0

    async def validate_jwt(self, token: str) -> dict:
        if self.revoked:
            raise TokenRevokedError("revoked")
        if self.rejected or self.claims is None:
            raise ValueError("invalid token")
        return self.claims

    async def validate_opaque(self, token: str) -> dict:
        self.opaque_validations += 1
        return await self.validate_jwt(token)


def _install(context, jwks_configured: bool = True) -> None:
    """Patch the three clients used by the authentication dependency."""
    server = context.auth_server
    jwks = MagicMock()
    jwks.is_configured = jwks_configured
    introspection = MagicMock()
    introspection.validate_token_with_introspection = AsyncMock(side_effect=server.validate_jwt)
    introspection.validate_opaque_token = AsyncMock(side_effect=server.validate_opaque)
    exchange = MagicMock()
    exchange.is_configured = False
    context.exchange = exchange
    for name, fake in (
        ("jwks_manager", jwks),
        ("introspection_client", introspection),
        ("token_exchange_client", exchange),
    ):
        patcher = patch(f"team.auth.dependencies.{name}", fake)
        patcher.start()
        context.add_cleanup(patcher.stop)


def _server(context) -> FakeAuthServer:
    if getattr(context, "auth_server", None) is None:
        context.auth_server = FakeAuthServer()
        _install(context)
    return context.auth_server


@given('an authentication server that knows the user "{user_id}" with scopes "{scopes}"')
def step_user(context, user_id: str, scopes: str) -> None:
    _server(context).claims = {"sub": user_id, "scope": scopes, "client_id": "web"}


@given(
    'an authentication server that knows the machine client "{client_id}" with scopes "{scopes}"'
)
def step_machine(context, client_id: str, scopes: str) -> None:
    _server(context).claims = {"sub": client_id, "client_id": client_id, "scope": scopes}


@given("an authentication server that revokes every token")
def step_revokes(context) -> None:
    _server(context).revoked = True


@given("an authentication server that rejects every token")
def step_rejects(context) -> None:
    _server(context).rejected = True


@given("OAuth2 is not configured")
def step_not_configured(context) -> None:
    context.auth_server = FakeAuthServer()
    _install(context, jwks_configured=False)


@given("token exchange is enabled and denies the scope")
def step_exchange_denies(context) -> None:
    context.exchange.is_configured = True
    context.exchange.validate_token_scopes = AsyncMock(
        side_effect=TokenExchangeError("denied", error_code="insufficient_scope")
    )


@given('a protected endpoint requiring the scope "{scope}"')
def step_protected(context, scope: str) -> None:
    app = FastAPI()

    @app.get("/protected")
    async def protected(auth: AuthContext = Depends(require_scopes(scope))) -> dict:
        return {
            "user_id": auth.user_id,
            "scopes": auth.scopes,
            "machine": auth.user.is_machine_client,
        }

    context.protected = TestClient(app)
    context.add_cleanup(context.protected.close)


@when("I call the protected endpoint without a token")
def step_call_without_token(context) -> None:
    context.response = context.protected.get("/protected")


@when('I call the protected endpoint with the token "{token}"')
def step_call_with_token(context, token: str) -> None:
    context.response = context.protected.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )


@then('the response detail is "{detail}"')
def step_detail(context, detail: str) -> None:
    assert context.response.json()["detail"] == detail, context.response.json()


@then('the authenticated user id is "{user_id}"')
def step_user_id(context, user_id: str) -> None:
    assert context.response.json()["user_id"] == user_id, context.response.json()


@then("the authenticated user is a machine client")
def step_is_machine(context) -> None:
    assert context.response.json()["machine"] is True


@then("the authenticated user is not a machine client")
def step_not_machine(context) -> None:
    assert context.response.json()["machine"] is False


@then("the authentication server validated {count:d} opaque token")
def step_opaque_count(context, count: int) -> None:
    assert context.auth_server.opaque_validations == count


@when("the user is built from the claims '{claims}'")
def step_build_user(context, claims: str) -> None:
    context.user = User.from_jwt_claims(json.loads(claims))


@then('the user has the scopes "{scopes}"')
def step_user_scopes(context, scopes: str) -> None:
    assert context.user.scopes == [s.strip() for s in scopes.split(",")], context.user.scopes
