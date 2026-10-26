# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions that authenticate the scenario's requests."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from behave import given
from vpn_portal.auth.models import User


@given('I am authenticated with "{scope}" scope')
def step_authenticated_with_scope(context, scope):
    scopes = [scope] if scope == "vpn:server" else [scope, "openid", "profile", "email"]
    _authenticate(context, scopes)


@given('I am authenticated with the scopes "{scopes}"')
def step_authenticated_with_scopes(context, scopes):
    _authenticate(context, scopes.split())


def _authenticate(context, scopes):
    user = User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=scopes,
        client_id="test-client",
    )
    claims = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "scope": " ".join(user.scopes),
        "client_id": user.client_id,
    }

    for target in ("jwks_manager", "introspection_client", "token_exchange_client"):
        patcher = patch(f"vpn_portal.auth.dependencies.{target}")
        mock = patcher.start()
        context.add_cleanup(patcher.stop)
        if target == "jwks_manager":
            mock.is_configured = True
        elif target == "introspection_client":
            mock.validate_token_with_introspection = AsyncMock(return_value=claims)
            mock.validate_opaque_token = AsyncMock(return_value=claims)
        else:
            mock.is_configured = False

    context.user = user
    context.headers["Authorization"] = "Bearer header.payload.signature"
