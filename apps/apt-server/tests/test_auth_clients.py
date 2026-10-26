# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Introspection, token exchange and userinfo clients."""

import json

import httpx
import jwt
import pytest
from apt_server.auth.introspection import IntrospectionClient, TokenRevokedError
from apt_server.auth.token_exchange import TokenExchangeClient, TokenExchangeError
from apt_server.auth.userinfo import UserInfoClient

ISSUER = "https://issuer.example"


def transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def discovery(monkeypatch: pytest.MonkeyPatch):
    from apt_server.auth.jwks import jwks_manager

    async def config() -> dict:
        return {
            "token_endpoint": f"{ISSUER}/oauth2/token",
            "userinfo_endpoint": f"{ISSUER}/userinfo",
        }

    monkeypatch.setattr(jwks_manager, "fetch_issuer_config", config)


# --- introspection ---------------------------------------------------------


async def test_introspection_reports_active_token(oidc_settings) -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"active": True})

    client = IntrospectionClient()
    client._http_client = transport(handler)

    assert await client.introspect_token("tok") is True
    assert seen[0]["token"] == "tok"
    assert seen[0]["client_id"] == "apt-client"
    assert seen[0]["token_type_hint"] == "access_token"
    assert client.introspection_uri == f"{ISSUER}/oauth2/introspect"


async def test_introspection_reports_inactive_token(oidc_settings) -> None:
    client = IntrospectionClient()
    client._http_client = transport(lambda r: httpx.Response(200, json={"active": False}))

    assert await client.introspect_token("tok") is False


async def test_introspection_skipped_when_not_configured(oidc_settings, monkeypatch) -> None:
    monkeypatch.setattr(oidc_settings, "oauth2_client_secret", "")

    assert IntrospectionClient().is_configured is False
    assert await IntrospectionClient().introspect_token("tok") is True


async def test_introspection_fails_open_on_transport_error(oidc_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = IntrospectionClient()
    client._http_client = transport(handler)

    assert await client.introspect_token("tok") is True


async def test_introspection_uses_and_fills_redis_cache(oidc_settings, monkeypatch, fake_redis):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"active": True})

    monkeypatch.setattr(oidc_settings, "redis_url", "redis://fake")
    client = IntrospectionClient()
    client._redis_client = fake_redis
    client._http_client = transport(handler)

    assert await client.introspect_token("tok") is True
    assert await client.introspect_token("tok") is True

    assert calls == 1
    (key,) = fake_redis.store
    assert key.startswith("apt_server:introspect:")
    assert fake_redis.store[key] == "1"
    assert fake_redis.ttls[key] == oidc_settings.token_introspection_cache_ttl


async def test_introspection_ignores_redis_failures(oidc_settings, monkeypatch, failing_redis):
    monkeypatch.setattr(oidc_settings, "redis_url", "redis://fake")
    client = IntrospectionClient()
    client._redis_client = failing_redis
    client._http_client = transport(lambda r: httpx.Response(200, json={"active": False}))

    assert await client.introspect_token("tok") is False


async def test_opaque_token_validated_by_introspection_only(oidc_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "token_type_hint" not in request.content.decode()
        return httpx.Response(200, json={"active": True, "sub": "u1", "scope": "apt:read"})

    client = IntrospectionClient()
    client._http_client = transport(handler)

    claims = await client.validate_opaque_token("gab_pat_x")

    assert claims["sub"] == "u1"


async def test_opaque_token_inactive_is_revoked(oidc_settings) -> None:
    client = IntrospectionClient()
    client._http_client = transport(lambda r: httpx.Response(200, json={"active": False}))

    with pytest.raises(TokenRevokedError):
        await client.validate_opaque_token("gab_pat_x")


async def test_opaque_token_request_failure_is_invalid(oidc_settings) -> None:
    client = IntrospectionClient()
    client._http_client = transport(lambda r: httpx.Response(500))

    with pytest.raises(jwt.InvalidTokenError):
        await client.validate_opaque_token("gab_pat_x")


async def test_jwt_validation_combines_signature_and_introspection(oidc_settings, monkeypatch):
    from apt_server.auth.jwks import jwks_manager

    async def validate(token: str) -> dict:
        return {"sub": "u1"}

    monkeypatch.setattr(jwks_manager, "validate_token", validate)
    client = IntrospectionClient()
    client._http_client = transport(lambda r: httpx.Response(200, json={"active": True}))

    assert await client.validate_token_with_introspection("a.b.c") == {"sub": "u1"}

    client._http_client = transport(lambda r: httpx.Response(200, json={"active": False}))
    with pytest.raises(TokenRevokedError):
        await client.validate_token_with_introspection("a.b.c")


async def test_introspection_close_releases_clients(oidc_settings, fake_redis) -> None:
    client = IntrospectionClient()
    client._http_client = transport(lambda r: httpx.Response(200))
    client._redis_client = fake_redis

    await client.close()

    assert client._http_client is None and client._redis_client is None
    assert fake_redis.closed


# --- token exchange --------------------------------------------------------


async def test_exchange_posts_rfc8693_request(oidc_settings, discovery) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(httpx.QueryParams(request.content.decode()))
        return httpx.Response(200, json={"access_token": "x", "scope": "apt:write"})

    client = TokenExchangeClient()
    client._http_client = transport(handler)

    result = await client.exchange_token("subject", ["apt:write"])

    assert result["scope"] == "apt:write"
    assert seen["grant_type"] == TokenExchangeClient.GRANT_TYPE
    assert seen["subject_token"] == "subject"
    assert seen["scope"] == "apt:write"


async def test_exchange_requires_configuration(oidc_settings, monkeypatch) -> None:
    monkeypatch.setattr(oidc_settings, "oauth2_client_id", "")

    with pytest.raises(TokenExchangeError, match="not configured"):
        await TokenExchangeClient().exchange_token("subject")


async def test_exchange_error_carries_error_code(oidc_settings, discovery) -> None:
    body = {"error": "insufficient_scope", "error_description": "nope"}
    client = TokenExchangeClient()
    client._http_client = transport(lambda r: httpx.Response(403, json=body))

    with pytest.raises(TokenExchangeError) as info:
        await client.exchange_token("subject", ["apt:write"])

    assert info.value.error_code == "insufficient_scope"
    assert "nope" in str(info.value)


async def test_exchange_error_without_json_body(oidc_settings, discovery) -> None:
    client = TokenExchangeClient()
    client._http_client = transport(lambda r: httpx.Response(502, content=b"<html>"))

    with pytest.raises(TokenExchangeError) as info:
        await client.exchange_token("subject")

    assert info.value.error_code == "unknown_error"


async def test_exchange_results_are_cached(oidc_settings, discovery, monkeypatch, fake_redis):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"access_token": "x"})

    monkeypatch.setattr(oidc_settings, "redis_url", "redis://fake")
    client = TokenExchangeClient()
    client._redis_client = fake_redis
    client._http_client = transport(handler)

    await client.exchange_token("subject", ["b", "a"])
    await client.exchange_token("subject", ["a", "b"])

    assert calls == 1
    (key,) = fake_redis.store
    assert ":tex:" in key
    assert json.loads(fake_redis.store[key]) == {"access_token": "x"}


async def test_validate_token_scopes_adds_claims(oidc_settings, discovery, monkeypatch) -> None:
    from apt_server.auth.jwks import jwks_manager

    async def validate(token: str) -> dict:
        return {"sub": "u1"}

    monkeypatch.setattr(jwks_manager, "validate_token", validate)
    client = TokenExchangeClient()
    client._http_client = transport(lambda r: httpx.Response(200, json={"access_token": "x"}))

    result = await client.validate_token_scopes("subject", ["apt:read"])

    assert result["claims"] == {"sub": "u1"}


async def test_validate_token_scopes_tolerates_unparsable_exchange(
    oidc_settings, discovery, monkeypatch
):
    from apt_server.auth.jwks import jwks_manager

    async def validate(token: str) -> dict:
        raise jwt.InvalidTokenError("bad")

    monkeypatch.setattr(jwks_manager, "validate_token", validate)
    client = TokenExchangeClient()
    client._http_client = transport(lambda r: httpx.Response(200, json={"access_token": "x"}))

    result = await client.validate_token_scopes("subject", ["apt:read"])

    assert "claims" not in result


# --- userinfo --------------------------------------------------------------


async def test_userinfo_fetches_profile_with_bearer(oidc_settings, discovery) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"sub": "u1", "email": "a@example.com"})

    client = UserInfoClient()
    client._http_client = transport(handler)

    assert (await client.get_userinfo("tok"))["email"] == "a@example.com"


async def test_userinfo_requires_configuration(monkeypatch) -> None:
    from apt_server.config import settings

    monkeypatch.setattr(settings, "oauth2_issuer", "")

    with pytest.raises(ValueError, match="not configured"):
        await UserInfoClient().get_userinfo("tok")


async def test_userinfo_requires_endpoint_in_discovery(oidc_settings, monkeypatch) -> None:
    from apt_server.auth.jwks import jwks_manager

    async def config() -> dict:
        return {}

    monkeypatch.setattr(jwks_manager, "fetch_issuer_config", config)

    with pytest.raises(ValueError, match="userinfo_endpoint"):
        await UserInfoClient().get_userinfo("tok")


async def test_userinfo_http_error_propagates(oidc_settings, discovery) -> None:
    client = UserInfoClient()
    client._http_client = transport(lambda r: httpx.Response(401))

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_userinfo("tok")


async def test_userinfo_is_cached(oidc_settings, discovery, monkeypatch, fake_redis) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"sub": "u1"})

    monkeypatch.setattr(oidc_settings, "redis_url", "redis://fake")
    client = UserInfoClient()
    client._redis_client = fake_redis
    client._http_client = transport(handler)

    await client.get_userinfo("tok")
    await client.get_userinfo("tok")

    assert calls == 1
    assert next(iter(fake_redis.ttls.values())) == oidc_settings.userinfo_cache_ttl
