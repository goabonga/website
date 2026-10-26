# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the OAuth2 authentication feature."""

from unittest.mock import AsyncMock, patch

from backend.auth import AuthContext, CurrentUser, require_scopes
from backend.auth.introspection import TokenRevokedError
from behave import given, when
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

TARGET = "backend.auth.dependencies"


def _start(context, name, target):
    patcher = patch(f"{TARGET}.{target}")
    context.patches[name] = patcher
    return patcher.start()


@given('a protected API with the routes "/me" and "/admin"')
def step_protected_api(context):
    api = FastAPI()

    @api.get("/me")
    async def me(user: CurrentUser):
        return {"id": str(user.id), "email": user.email, "scopes": user.scopes}

    @api.get("/admin")
    async def admin(auth: AuthContext = Depends(require_scopes("api:read"))):
        return {"user_id": auth.user_id}

    context.client.close()
    context.client = TestClient(api, raise_server_exceptions=False)

    jwks = _start(context, "jwks", "jwks_manager")
    jwks.is_configured = True
    exchange = _start(context, "exchange", "token_exchange_client")
    exchange.is_configured = False
    context.introspection = _start(context, "introspection", "introspection_client")


@given("OAuth2 is not configured")
def step_oauth2_not_configured(context):
    context.patches["jwks"].stop()
    jwks = _start(context, "jwks", "jwks_manager")
    jwks.is_configured = False


@given('the token "{token}" is valid with the claims:')
def step_valid_token(context, token):
    claims = {row["claim"]: row["value"] for row in context.table}
    context.introspection.validate_token_with_introspection = AsyncMock(return_value=claims)


@given('the token "{token}" has been revoked')
def step_revoked_token(context, token):
    context.introspection.validate_token_with_introspection = AsyncMock(
        side_effect=TokenRevokedError("revoked")
    )


@when('I request "{path}" with the bearer token "{token}"')
def step_get_with_token(context, path, token):
    context.response = context.client.get(path, headers={"Authorization": f"Bearer {token}"})
