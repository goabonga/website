# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The fake provider's introspection, revocation and userinfo endpoints."""

import time

import jwt
import pytest
from e2e_support.oidc import User
from test_oidc_token import (
    ADA,
    claims_of,
    credentials,
    error,
    exchange,
    login_tokens,
    make_provider,
    refresh,
    serve,
    user_token,
)

SERVICE = ("service", "service-secret")


@pytest.fixture
def http():
    with serve(make_provider()) as client:
        yield client


def introspect(http, token, client=SERVICE, **data):
    return http.post("/oauth2/introspect", data={"token": token, **data}, auth=client)


def revoke(http, token, client=SERVICE, **data):
    return http.post("/oauth2/revoke", data={"token": token, **data}, auth=client)


def userinfo(http, token, method="GET"):
    return http.request(method, "/userinfo", headers={"Authorization": f"Bearer {token}"})


# -- introspection --------------------------------------------------------------------


def test_an_active_access_token_is_described(http):
    token = login_tokens(http)["access_token"]
    claims = claims_of(http, token)
    response = introspect(http, token)
    assert response.status_code == 200
    assert response.json() == {
        "active": True,
        "scope": "openid profile email",
        "client_id": "web",
        "token_type": "Bearer",
        "exp": claims["exp"],
        "iat": claims["iat"],
        "sub": ADA.id,
        "aud": "web",
        "iss": claims["iss"],
        "jti": claims["jti"],
    }


def test_the_client_secret_may_be_sent_in_the_form(http):
    token = login_tokens(http)["access_token"]
    response = http.post(
        "/oauth2/introspect",
        data={"token": token, "client_id": "service", "client_secret": "service-secret"},
    )
    assert response.json()["active"] is True


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_tokens_the_provider_never_issued_are_inactive(http, token):
    assert introspect(http, token).json() == {"active": False}


def test_a_token_signed_elsewhere_with_an_unknown_jti_is_inactive(http):
    foreign = jwt.encode({"jti": "unknown"}, "k" * 32, algorithm="HS256")
    assert introspect(http, foreign).json() == {"active": False}


def test_an_expired_token_is_inactive():
    provider = make_provider(access_token_ttl=60)
    with serve(provider) as http:
        token = login_tokens(http)["access_token"]
        assert introspect(http, token).json()["active"] is True
        provider.clock = lambda: time.time() + 61
        assert introspect(http, token).json() == {"active": False}


def test_refresh_tokens_can_be_introspected(http):
    tokens = login_tokens(http)
    for hint in ({}, {"token_type_hint": "refresh_token"}):
        body = introspect(http, tokens["refresh_token"], **hint).json()
        assert body["active"] is True
        assert body["token_type"] == "refresh_token"
        assert body["client_id"] == "web"
        assert body["sub"] == ADA.id
    refresh(http, tokens["refresh_token"])
    assert introspect(http, tokens["refresh_token"]).json() == {"active": False}


def test_an_access_token_is_found_even_with_a_refresh_hint(http):
    token = login_tokens(http)["access_token"]
    assert introspect(http, token, token_type_hint="refresh_token").json()["active"] is True


@pytest.mark.parametrize(
    ("client", "status", "expected"),
    [
        (None, 401, ("invalid_client", "Client authentication required")),
        (("ghost", "x"), 401, ("invalid_client", "Invalid client")),
        (("service", "wrong"), 401, ("invalid_client", "Invalid client credentials")),
        (
            ("narrow", "narrow-secret"),
            403,
            ("insufficient_scope", "Client is not authorized to introspect tokens"),
        ),
    ],
)
def test_only_an_authenticated_client_with_the_introspect_scope_may_introspect(
    http, client, status, expected
):
    response = introspect(http, "x", client=client)
    assert response.status_code == status
    assert error(response) == expected


def test_a_public_client_without_the_scope_is_refused(http):
    response = http.post("/oauth2/introspect", data={"token": "x", "client_id": "web"})
    assert response.status_code == 403


# -- revocation -----------------------------------------------------------------------


def test_a_revoked_access_token_is_dead_everywhere(http):
    token = login_tokens(http)["access_token"]
    assert revoke(http, token).status_code == 200
    assert introspect(http, token).json() == {"active": False}
    assert userinfo(http, token).json() == {"detail": "Access token has been revoked"}
    assert error(exchange(http, token, "billing:read")) == (
        "invalid_request",
        "Subject token not found or revoked",
    )


def test_a_revoked_refresh_token_cannot_be_used(http):
    tokens = login_tokens(http)
    assert revoke(http, tokens["refresh_token"], token_type_hint="refresh_token").status_code == 200
    assert error(refresh(http, tokens["refresh_token"]))[0] == "invalid_grant"


def test_revoking_an_unknown_token_still_answers_200(http):
    assert revoke(http, "never-issued").status_code == 200
    assert revoke(http, "a.b.c").status_code == 200


def test_the_revocation_endpoint_authenticates_the_client(http):
    response = revoke(http, "x", client=("service", "wrong"))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"
    assert revoke(http, "x", client=None).status_code == 401


def test_a_public_client_can_revoke_its_token(http):
    tokens = login_tokens(http)
    response = http.post(
        "/oauth2/revoke", data={"token": tokens["access_token"], "client_id": "web"}
    )
    assert response.status_code == 200
    assert introspect(http, tokens["access_token"]).json() == {"active": False}


def test_an_administrator_can_revoke_every_token_or_those_of_one_user():
    provider = make_provider()
    with serve(provider) as http:
        ada = login_tokens(http, login_hint="ada@example.test")["access_token"]
        root = login_tokens(http, login_hint="root@example.test")["access_token"]
        provider.revoke_tokens(user_id=ADA.id)
        assert introspect(http, ada).json()["active"] is False
        assert introspect(http, root).json()["active"] is True
        provider.revoke_tokens()
        assert introspect(http, root).json()["active"] is False


# -- userinfo -------------------------------------------------------------------------


def test_userinfo_returns_the_claims_allowed_by_the_scopes():
    provider = make_provider()
    provider.add_user(
        User(
            email="lin@example.test",
            name="Lin",
            picture="https://img.example.test/lin.png",
            id="33333333-3333-4333-8333-333333333333",
            email_verified=False,
        )
    )
    with serve(provider) as http:
        token = login_tokens(http, login_hint="lin@example.test")["access_token"]
        assert userinfo(http, token).json() == {
            "sub": "33333333-3333-4333-8333-333333333333",
            "name": "Lin",
            "picture": "https://img.example.test/lin.png",
            "email": "lin@example.test",
            "email_verified": False,
        }
        assert userinfo(http, token, method="POST").status_code == 200


def test_userinfo_is_limited_by_the_scopes_of_the_token(http):
    token = login_tokens(http, scope="openid")["access_token"]
    assert userinfo(http, token).json() == {"sub": ADA.id}
    profile = login_tokens(http, scope="openid profile")["access_token"]
    assert userinfo(http, profile).json() == {"sub": ADA.id, "name": "Ada"}


def test_userinfo_uses_the_pairwise_subject_of_the_client():
    with serve(make_provider(pairwise_subjects=True)) as http:
        token = login_tokens(http)["access_token"]
        assert userinfo(http, token).json()["sub"] == claims_of(http, token)["sub"]
        assert userinfo(http, token).json()["sub"] != ADA.id


@pytest.mark.parametrize(
    ("headers", "detail"),
    [
        ({}, "Invalid access token"),
        ({"Authorization": "Bearer garbage"}, "Invalid access token"),
        ({"Authorization": "Basic abc"}, "Invalid access token"),
    ],
)
def test_userinfo_rejects_missing_and_malformed_tokens(http, headers, detail):
    response = http.get("/userinfo", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": detail}
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'


def test_userinfo_rejects_unknown_and_tokenless_jwts(http):
    unknown = jwt.encode({"jti": "nope"}, "k" * 32, algorithm="HS256")
    no_jti = jwt.encode({"sub": "x"}, "k" * 32, algorithm="HS256")
    assert userinfo(http, unknown).json() == {"detail": "Access token not found"}
    assert userinfo(http, no_jti).json() == {"detail": "Invalid access token"}


def test_userinfo_rejects_expired_tokens():
    provider = make_provider(access_token_ttl=60)
    with serve(provider) as http:
        token = login_tokens(http)["access_token"]
        provider.clock = lambda: time.time() + 61
        assert userinfo(http, token).json() == {"detail": "Access token has expired"}


def test_userinfo_needs_the_openid_scope(http):
    exchanged = exchange(http, user_token(http), "billing:read").json()["access_token"]
    response = userinfo(http, exchanged)
    assert response.status_code == 403
    assert response.json() == {"detail": "Access token does not have openid scope"}
    assert response.headers["www-authenticate"] == 'Bearer error="insufficient_scope"'


def test_userinfo_needs_a_user(http):
    machine = credentials(http, scope="openid").json()["access_token"]
    assert userinfo(http, machine).json() == {"detail": "Access token has no associated user"}


def test_userinfo_of_a_removed_user_is_refused():
    provider = make_provider()
    with serve(provider) as http:
        token = login_tokens(http)["access_token"]
        del provider.users[ADA.id]
        assert userinfo(http, token).json() == {"detail": "User not found or inactive"}


def test_the_calls_are_recorded(http):
    token = login_tokens(http)["access_token"]
    introspect(http, token)
    userinfo(http, token)
    revoke(http, token)
    provider = http.provider
    assert provider.last_request("/oauth2/introspect").json["active"] is True
    assert provider.last_request("/userinfo").headers["authorization"] == f"Bearer {token}"
    assert provider.last_request("/oauth2/revoke").form["token"] == token
