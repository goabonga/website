# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the OAuth2 bearer authentication feature.

The identity provider is replaced by a local RSA key pair: tokens are signed
here and the JWKS client of the validator is replaced by a fake that returns
the matching public key. Nothing leaves the process.
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
from behave import given, when
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI

from knowledge.auth import dependencies
from knowledge.auth import jwt as jwt_module
from knowledge.auth.dependencies import AuthContext, require_scopes
from knowledge.config import get_settings
from knowledge.database import get_db


def _generate_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwksClient:
    """Stands in for PyJWKClient and serves a single public key."""

    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.public_key)


def _build_probe_app(scope: str) -> FastAPI:
    probe = FastAPI()

    @probe.get("/probe")
    async def probe_endpoint(auth: AuthContext = Depends(require_scopes(scope))):
        return {"user_id": str(auth.user_id), "tenant_id": str(auth.tenant_id)}

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    async def fake_db():
        yield session

    probe.dependency_overrides[get_db] = fake_db
    return probe


@given('an identity provider that signs tokens for the issuer "{issuer}"')
def step_identity_provider(context, issuer):
    context.issuer = issuer
    context.signing_key = _generate_key()

    settings = get_settings()
    for name, value in (
        ("oauth2_issuer", issuer),
        ("oauth2_client_id", ""),
        ("oauth2_client_secret", ""),
    ):
        patcher = patch.object(settings, name, value)
        patcher.start()
        context.add_cleanup(patcher.stop)

    jwt_module._jwt_validator = None
    validator = jwt_module.get_jwt_validator()
    validator._jwks_client = FakeJwksClient(context.signing_key.public_key())
    context.add_cleanup(setattr, jwt_module, "_jwt_validator", None)
    assert dependencies.settings.oauth2_issuer == issuer


@given('a protected endpoint requiring the scope "{scope}"')
def step_protected_endpoint(context, scope):
    context.probe = _build_probe_app(scope)


def _sign(context, user_id, scopes, key=None, expires_in=300):
    now = int(time.time())
    claims = {
        "sub": user_id,
        "iss": context.issuer,
        "iat": now - 10,
        "exp": now + expires_in,
        "scope": scopes,
    }
    return jwt.encode(claims, key or context.signing_key, algorithm="RS256")


@given('a signed token for user "{user_id}" with scopes "{scopes}"')
def step_signed_token(context, user_id, scopes):
    context.token = _sign(context, user_id, scopes)


@given('an expired token for user "{user_id}" with scopes "{scopes}"')
def step_expired_token(context, user_id, scopes):
    context.token = _sign(context, user_id, scopes, expires_in=-60)


@given('a token signed by another key for user "{user_id}" with scopes "{scopes}"')
def step_foreign_token(context, user_id, scopes):
    context.token = _sign(context, user_id, scopes, key=_generate_key())


@when("I call the protected endpoint without a token")
def step_call_without_token(context):
    context.response = context.call_app(context.probe, "GET", "/probe")


@when("I call the protected endpoint with the token")
def step_call_with_token(context):
    context.response = context.call_app(
        context.probe, "GET", "/probe", headers={"Authorization": f"Bearer {context.token}"}
    )


@when('I call the protected endpoint with the token and tenant "{tenant}"')
def step_call_with_tenant(context, tenant):
    context.response = context.call_app(
        context.probe,
        "GET",
        "/probe",
        headers={"Authorization": f"Bearer {context.token}", "X-Tenant-ID": tenant},
    )
