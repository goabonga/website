# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWKS manager: discovery, caching and JWT validation."""

import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from apt_server.auth.jwks import JWKSManager
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://issuer.example"


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def mint(private_key, **overrides) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": "user-1", "iat": now, "exp": now + 300, **overrides}
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def manager(oidc_settings, private_key) -> JWKSManager:
    mgr = JWKSManager()

    async def fake_config() -> dict:
        return {"jwks_uri": f"{ISSUER}/jwks"}

    mgr.fetch_issuer_config = fake_config  # type: ignore[method-assign]
    mgr._get_jwks_client = lambda uri: SimpleNamespace(  # type: ignore[method-assign]
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key())
    )
    return mgr


def test_not_configured_without_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    from apt_server.config import settings

    monkeypatch.setattr(settings, "oauth2_issuer", "")

    assert JWKSManager().is_configured is False


def test_issuer_strips_trailing_slash_and_lists_trusted(oidc_settings, monkeypatch) -> None:
    monkeypatch.setattr(oidc_settings, "oauth2_issuer", f"{ISSUER}/")
    monkeypatch.setattr(
        oidc_settings, "oauth2_trusted_issuers", "https://b.example, https://c.example"
    )

    mgr = JWKSManager()

    assert mgr.issuer == ISSUER
    assert mgr.accepted_issuers == [ISSUER, "https://b.example", "https://c.example"]


async def test_validate_token_returns_claims(manager, private_key) -> None:
    claims = await manager.validate_token(mint(private_key, scope="apt:read"))

    assert claims["sub"] == "user-1"
    assert claims["scope"] == "apt:read"


async def test_validate_token_accepts_trusted_issuer(
    manager, private_key, oidc_settings, monkeypatch
):
    monkeypatch.setattr(oidc_settings, "oauth2_trusted_issuers", "https://other.example")

    claims = await manager.validate_token(mint(private_key, iss="https://other.example"))

    assert claims["iss"] == "https://other.example"


async def test_validate_token_rejects_unknown_issuer(manager, private_key) -> None:
    with pytest.raises(jwt.InvalidTokenError):
        await manager.validate_token(mint(private_key, iss="https://evil.example"))


async def test_validate_token_rejects_expired_token(manager, private_key) -> None:
    with pytest.raises(jwt.ExpiredSignatureError):
        await manager.validate_token(mint(private_key, exp=int(time.time()) - 10))


async def test_validate_token_rejects_foreign_signature(manager) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(jwt.InvalidTokenError):
        await manager.validate_token(mint(other))


async def test_validate_token_requires_configuration(monkeypatch) -> None:
    from apt_server.config import settings

    monkeypatch.setattr(settings, "oauth2_issuer", "")

    with pytest.raises(ValueError, match="not configured"):
        await JWKSManager().validate_token("a.b.c")


async def test_validate_token_requires_jwks_uri(oidc_settings) -> None:
    mgr = JWKSManager()

    async def no_uri() -> dict:
        return {}

    mgr.fetch_issuer_config = no_uri  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="JWKS URI"):
        await mgr.validate_token("a.b.c")


async def test_signing_key_failure_becomes_invalid_token(oidc_settings) -> None:
    from jwt import PyJWKClientError

    mgr = JWKSManager()

    async def config() -> dict:
        return {"jwks_uri": f"{ISSUER}/jwks"}

    def boom(token: str):
        raise PyJWKClientError("no key")

    mgr.fetch_issuer_config = config  # type: ignore[method-assign]
    mgr._get_jwks_client = lambda uri: SimpleNamespace(get_signing_key_from_jwt=boom)  # type: ignore[method-assign]

    with pytest.raises(jwt.InvalidTokenError, match="signing key"):
        await mgr.validate_token("a.b.c")


async def test_issuer_config_is_fetched_once_then_cached(oidc_settings) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"jwks_uri": "https://issuer.example/jwks"})

    mgr = JWKSManager()
    mgr._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    first = await mgr.fetch_issuer_config()
    second = await mgr.fetch_issuer_config()

    assert first == second == {"jwks_uri": "https://issuer.example/jwks"}
    assert calls == [f"{ISSUER}/.well-known/openid-configuration"]
    await mgr.close()
    assert mgr._http_client is None


async def test_issuer_config_requires_configuration(monkeypatch) -> None:
    from apt_server.config import settings

    monkeypatch.setattr(settings, "oauth2_issuer", "")

    with pytest.raises(ValueError):
        await JWKSManager().fetch_issuer_config()
