# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Configuration, discovery, JWKS and request recording of the fake OpenID provider."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import jwt
import pytest
from e2e_support.oidc import Client, FakeOIDCProvider, User
from e2e_support.oidc.models import (
    client_scope_matches,
    exchange_scope_matches,
    user_has_scope,
)
from e2e_support.server import LiveServer


@pytest.fixture
def provider():
    return FakeOIDCProvider(
        users=[User(email="ada@example.test", name="Ada")],
        clients=[Client.public("web", ["http://127.0.0.1:*/callback"])],
    )


@pytest.fixture
def served(provider):
    with LiveServer(provider) as server:
        yield server


def test_the_issuer_is_learned_from_the_live_server(provider, served):
    assert provider.issuer == served.url


def test_the_issuer_is_unknown_until_the_provider_is_served(provider):
    with pytest.raises(RuntimeError, match="issuer is not known"):
        provider.issuer  # noqa: B018


def test_an_explicit_issuer_is_kept_without_trailing_slash():
    assert (
        FakeOIDCProvider(issuer="https://auth.example.test/").issuer == "https://auth.example.test"
    )


def test_discovery_lists_the_endpoints_of_the_auth_application(served):
    document = httpx.get(f"{served.url}/.well-known/openid-configuration").json()
    assert document["issuer"] == served.url
    assert document["authorization_endpoint"] == f"{served.url}/oauth2/authorize"
    assert document["token_endpoint"] == f"{served.url}/oauth2/token"
    assert document["userinfo_endpoint"] == f"{served.url}/userinfo"
    assert document["jwks_uri"] == f"{served.url}/.well-known/jwks.json"
    assert document["introspection_endpoint"] == f"{served.url}/oauth2/introspect"
    assert document["revocation_endpoint"] == f"{served.url}/oauth2/revoke"
    assert document["id_token_signing_alg_values_supported"] == ["RS256"]
    assert document["code_challenge_methods_supported"] == ["S256", "plain"]
    assert "urn:ietf:params:oauth:grant-type:token-exchange" in document["grant_types_supported"]


def test_discovery_without_an_explicit_issuer_uses_the_request_address():
    async def fetch():
        transport = httpx.ASGITransport(app=FakeOIDCProvider())
        async with httpx.AsyncClient(transport=transport, base_url="http://in-process.test") as c:
            return (await c.get("/.well-known/openid-configuration")).json()

    # A thread of its own: a started Playwright session keeps the main thread's loop busy.
    with ThreadPoolExecutor(max_workers=1) as pool:
        document = pool.submit(asyncio.run, fetch()).result()
    assert document["issuer"] == "http://in-process.test"


def test_pairwise_subjects_are_advertised():
    provider = FakeOIDCProvider(issuer="http://x.test", pairwise_subjects=True)
    assert provider.discovery_document("http://x.test")["subject_types_supported"] == ["pairwise"]


def test_the_jwks_key_verifies_what_the_provider_signs(provider, served):
    token = provider.key.sign({"iss": served.url, "sub": "someone"})
    jwks_client = jwt.PyJWKClient(f"{served.url}/.well-known/jwks.json")
    key = jwks_client.get_signing_key_from_jwt(token)
    assert jwt.decode(token, key.key, algorithms=["RS256"], issuer=served.url)["sub"] == "someone"
    document = httpx.get(f"{served.url}/.well-known/jwks.json").json()
    assert set(document["keys"][0]) == {"kty", "n", "e", "kid", "use", "alg"}
    assert document["keys"][0]["kid"] == provider.key.kid


def test_every_provider_generates_its_own_key():
    assert FakeOIDCProvider().key.kid != FakeOIDCProvider().key.kid


def test_requests_are_recorded_for_assertions(provider, served):
    httpx.get(f"{served.url}/.well-known/jwks.json", params={"probe": "1"})
    httpx.get(f"{served.url}/.well-known/openid-configuration")
    record = provider.last_request("/.well-known/jwks.json")
    assert (record.method, record.status, record.query) == ("GET", 200, {"probe": "1"})
    assert record.json["keys"][0]["kid"] == provider.key.kid
    assert [r.path for r in provider.requests] == [
        "/.well-known/jwks.json",
        "/.well-known/openid-configuration",
    ]
    assert provider.requests_to("/.well-known/jwks.json", method="get") == [record]
    assert provider.requests_to("/nothing") == []
    with pytest.raises(LookupError, match="no request for /nothing"):
        provider.last_request("/nothing")
    provider.clear_requests()
    assert provider.requests == []


def test_unknown_paths_are_recorded_with_their_status(provider, served):
    httpx.get(f"{served.url}/unknown")
    assert provider.last_request("/unknown").status == 404


def test_users_and_clients_can_be_added_later(provider):
    grace = provider.add_user(User(email="Grace@Example.test"))
    client = provider.add_client(Client.service("svc", "s3cret", ["introspect"]))
    assert provider.user_by_email("grace@example.test") is grace
    assert provider.user_by_email("nobody@example.test") is None
    assert provider.clients["svc"] is client
    assert client.is_confidential
    assert not provider.clients["web"].is_confidential


def test_user_ids_are_uuids_and_distinct_by_default():
    first, second = User(email="a@x.test"), User(email="b@x.test")
    assert first.id != second.id
    with pytest.raises(ValueError, match="must be a UUID"):
        User(email="a@x.test", id="not-a-uuid")


def test_only_users_without_mfa_are_supported():
    with pytest.raises(ValueError, match="only 'none' is emulated"):
        User(email="a@x.test", mfa="totp")


@pytest.mark.parametrize(
    ("scope", "allowed", "expected"),
    [
        ("openid", ["openid"], True),
        ("openid", ["profile"], False),
        ("anything:at:all", ["*"], True),
        ("billing:read", ["billing:*"], True),
        ("billing:invoices:read", ["billing:*"], True),
        ("billing:invoices:read", ["billing:invoices:*"], True),
        ("billing", ["billing:*"], False),
        ("vpn:admin", ["billing:*"], False),
    ],
)
def test_client_scope_wildcards_follow_the_auth_application(scope, allowed, expected):
    assert client_scope_matches(scope, allowed) is expected


@pytest.mark.parametrize(
    ("scope", "allowed", "expected"),
    [
        ("billing:read", ["billing:read"], True),
        ("billing:read", ["billing:*"], True),
        ("billing:invoices:read", ["billing:*"], True),
        ("knowledge:read", ["internal:*"], True),
        ("billing:read", ["internal:*"], False),
        ("billing:read", ["*"], True),
        ("vpn:admin", ["billing:*"], False),
    ],
)
def test_exchange_scope_wildcards_follow_the_auth_application(scope, allowed, expected):
    assert exchange_scope_matches(scope, allowed) is expected


@pytest.mark.parametrize(
    ("held", "required", "expected"),
    [
        (["*"], "vpn:admin", True),
        (["billing:read"], "billing:read", True),
        (["billing:*"], "billing:write", True),
        (["billing:read"], "billing:write", False),
        (["internal:*"], "knowledge:read", False),
        ([], "billing:read", False),
    ],
)
def test_user_scopes_follow_the_role_rules_of_the_auth_application(held, required, expected):
    assert user_has_scope(held, required) is expected
