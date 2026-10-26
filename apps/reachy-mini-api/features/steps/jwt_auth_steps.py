# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the JWT authentication feature."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
from behave import given, when
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from reachy_mini_api.auth import AuthContext, jwks_manager, require_scopes
from reachy_mini_api.config import settings

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwksClient:
    """Stand-in for PyJWKClient that always returns the test public key."""

    def get_signing_key_from_jwt(self, token):
        """Return the test signing key."""
        return SimpleNamespace(key=PRIVATE_KEY.public_key())


def start_patch(context, patcher):
    """Start a patcher and register it for the end of the scenario."""
    patcher.start()
    context.patchers.append(patcher)


def issue_token(issuer, scopes, expires_in):
    """Sign a JWT with the test private key."""
    now = int(time.time())
    claims = {
        "sub": str(uuid4()),
        "iss": issuer,
        "iat": now - 10,
        "exp": now + expires_in,
        "scope": scopes,
    }
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256")


@given('a protected route requiring the scope "{scope}"')
def step_protected_route(context, scope):
    """Build an application with one route protected by the scope, and fake the JWKS."""
    protected = FastAPI()

    @protected.get("/protected")
    async def protected_route(auth: AuthContext = Depends(require_scopes(scope))):
        return {"user": auth.user_id}

    context.app = protected
    config = {"jwks_uri": f"{jwks_manager.issuer}/.well-known/jwks.json"}
    start_patch(
        context, patch.object(jwks_manager, "fetch_issuer_config", AsyncMock(return_value=config))
    )
    start_patch(context, patch.object(jwks_manager, "_jwks_client", FakeJwksClient()))


@given('"{issuer}" is a trusted issuer')
def step_trusted_issuer(context, issuer):
    """Add an additional trusted issuer."""
    context.setting_backup["oauth2_trusted_issuers"] = settings.oauth2_trusted_issuers
    settings.oauth2_trusted_issuers = issuer


@given('a token issued by the primary issuer with the scopes "{scopes}"')
def step_primary_token(context, scopes):
    """Create a valid token from the primary issuer."""
    context.token = issue_token(jwks_manager.issuer, scopes, 300)


@given('an expired token issued by the primary issuer with the scopes "{scopes}"')
def step_expired_token(context, scopes):
    """Create an expired token from the primary issuer."""
    context.token = issue_token(jwks_manager.issuer, scopes, -60)


@given('a token issued by "{issuer}" with the scopes "{scopes}"')
def step_issuer_token(context, issuer, scopes):
    """Create a valid token from the given issuer."""
    context.token = issue_token(issuer, scopes, 300)


@when('I send a GET request to "{path}" with that token')
def step_get_with_token(context, path):
    """Send a GET request carrying the token as a bearer token."""
    context.send_request("GET", path, {"Authorization": f"Bearer {context.token}"})
