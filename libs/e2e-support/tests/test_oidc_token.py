# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The fake provider's token endpoint: the four grants and client authentication."""

import base64
import contextlib
import hashlib
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from e2e_support.oidc import Client, FakeOIDCProvider, SigningKey, User, pkce
from e2e_support.oidc.models import AUTHORIZATION_CODE, CLIENT_CREDENTIALS, TOKEN_EXCHANGE
from e2e_support.server import LiveServer

CALLBACK = "http://127.0.0.1:9/auth/callback"
VERIFIER = "v" * 43
KEY = SigningKey()  # generating a key is slow: share one between providers
EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
ACCESS = "urn:ietf:params:oauth:token-type:access_token"
JWT_TYPE = "urn:ietf:params:oauth:token-type:jwt"

ADA = User(
    email="ada@example.test",
    name="Ada",
    id="11111111-1111-4111-8111-111111111111",
    scopes=("billing:read", "vpn:*"),
)
ROOT = User(email="root@example.test", id="22222222-2222-4222-8222-222222222222", scopes=("*",))


def make_provider(**options):
    return FakeOIDCProvider(
        users=[ADA, ROOT],
        clients=[
            Client.public(
                "web", [CALLBACK], allowed_scopes=("openid", "profile", "email", "offline_access")
            ),
            Client.public("other", [CALLBACK]),
            Client.public("api-web", [CALLBACK], allowed_scopes=("openid", "billing:read")),
            Client(
                "confidential-web",
                "web-secret",
                (CALLBACK,),
                grant_types=(AUTHORIZATION_CODE, "refresh_token"),
            ),
            Client.service(
                "service",
                "service-secret",
                ["openid", "profile", "email", "billing:*", "vpn:*", "introspect"],
            ),
            Client.service("narrow", "narrow-secret", ["billing:read"]),
            Client("no-grants", "s", grant_types=("password",)),
            Client("retired", "s", is_active=False),
        ],
        auto_approve=True,
        signing_key=KEY,
        **options,
    )


@contextlib.contextmanager
def serve(provider):
    with (
        LiveServer(provider) as server,
        httpx.Client(base_url=server.url, follow_redirects=False) as client,
    ):
        client.provider = provider
        yield client


@pytest.fixture
def http():
    with serve(make_provider()) as client:
        yield client


def get_code(http, client_id="web", scope="openid profile email", login_hint=None, **extra):
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "scope": scope,
        "state": "s",
        "code_challenge": pkce.challenge_for(VERIFIER),
        **extra,
    }
    if login_hint:
        params["login_hint"] = login_hint
    response = http.get("/oauth2/authorize", params=params)
    return parse_qs(urlparse(response.headers["location"]).query)["code"][0]


def redeem(http, code_value, client_id="web", **overrides):
    data = {
        "grant_type": "authorization_code",
        "code": code_value,
        "redirect_uri": CALLBACK,
        "client_id": client_id,
        "code_verifier": VERIFIER,
        **overrides,
    }
    return http.post("/oauth2/token", data={k: v for k, v in data.items() if v is not None})


def login_tokens(http, client_id="web", scope="openid profile email", login_hint=None):
    response = redeem(http, get_code(http, client_id, scope, login_hint), client_id)
    assert response.status_code == 200, response.text
    return response.json()


def exchange(http, subject_token, scope=None, client=("service", "service-secret"), **extra):
    data = {
        "grant_type": EXCHANGE,
        "subject_token": subject_token,
        "subject_token_type": ACCESS,
        **extra,
    }
    if scope is not None:
        data["scope"] = scope
    return http.post("/oauth2/token", data=data, auth=client)


def error(response):
    detail = response.json()["detail"]
    return detail["error"], detail["error_description"]


def claims_of(http, token, **options):
    key = jwt.PyJWKClient(f"{http.base_url}/.well-known/jwks.json").get_signing_key_from_jwt(token)
    return jwt.decode(
        token, key.key, algorithms=["RS256"], options={"verify_aud": False, **options}
    )


# -- authorization code ---------------------------------------------------------------


def test_the_code_is_exchanged_for_signed_tokens(http):
    tokens = login_tokens(http)
    assert tokens["token_type"] == "Bearer"
    assert tokens["expires_in"] == 3600
    assert tokens["scope"] == "openid profile email"
    assert tokens["refresh_token"]

    access = claims_of(http, tokens["access_token"])
    assert access["iss"] == str(http.base_url).rstrip("/")
    assert access["sub"] == ADA.id
    assert access["aud"] == "web"
    assert access["client_id"] == "web"
    assert access["scope"] == "openid profile email"
    assert access["exp"] - access["iat"] == 3600
    assert uuid.UUID(access["jti"])
    # a plain login carries no role scope and no profile claim, exactly like the auth app
    assert "billing:read" not in access["scope"]
    assert "email" not in access


def test_the_id_token_binds_nonce_auth_time_and_access_token(http):
    code = get_code(http, nonce="n-42")
    tokens = redeem(http, code).json()
    id_token = claims_of(http, tokens["id_token"])
    assert (id_token["sub"], id_token["aud"], id_token["nonce"]) == (ADA.id, "web", "n-42")
    digest = hashlib.sha256(tokens["access_token"].encode()).digest()
    assert id_token["at_hash"] == base64.urlsafe_b64encode(digest[:16]).rstrip(b"=").decode()
    assert id_token["auth_time"] <= int(time.time())
    assert claims_of(http, tokens["access_token"])["nonce"] == "n-42"


def test_without_the_openid_scope_there_is_no_id_token(http):
    tokens = login_tokens(http, scope="profile")
    assert "id_token" not in tokens


def test_a_code_can_only_be_redeemed_once(http):
    code = get_code(http)
    assert redeem(http, code).status_code == 200
    response = redeem(http, code)
    assert response.status_code == 400
    assert error(response) == ("invalid_grant", "Invalid or expired authorization code")


def test_an_expired_code_is_refused():
    provider = make_provider(code_ttl=60)
    with serve(provider) as http:
        code = get_code(http)
        provider.clock = lambda: time.time() + 61
        assert error(redeem(http, code))[0] == "invalid_grant"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"code": None}, ("invalid_request", "code is required")),
        ({"redirect_uri": None}, ("invalid_request", "redirect_uri is required")),
        ({"code": "unknown"}, ("invalid_grant", "Invalid or expired authorization code")),
        (
            {"redirect_uri": "http://127.0.0.1:9/other"},
            ("invalid_grant", "redirect_uri does not match"),
        ),
        ({"code_verifier": None}, ("invalid_request", "code_verifier is required")),
        ({"code_verifier": "short"}, ("invalid_request", "Invalid code_verifier format")),
        ({"code_verifier": "w" * 43}, ("invalid_grant", "PKCE verification failed")),
    ],
)
def test_authorization_code_validation(http, overrides, expected):
    response = redeem(http, get_code(http), **overrides)
    assert response.status_code == 400
    assert error(response) == expected


def test_a_failed_pkce_check_does_not_burn_the_code(http):
    code = get_code(http)
    assert redeem(http, code, code_verifier="w" * 43).status_code == 400
    assert redeem(http, code).status_code == 200


def test_a_code_belongs_to_the_client_that_asked_for_it(http):
    code = get_code(http, client_id="web")
    response = redeem(http, code, client_id="other")
    assert error(response) == ("invalid_grant", "Authorization code was not issued to this client")


def test_a_client_without_pkce_needs_no_verifier():
    provider = make_provider()
    provider.clients["web"].require_pkce = False
    with serve(provider) as http:
        code = parse_qs(
            urlparse(
                http.get(
                    "/oauth2/authorize",
                    params={"response_type": "code", "client_id": "web", "redirect_uri": CALLBACK},
                ).headers["location"]
            ).query
        )["code"][0]
        assert redeem(http, code, code_verifier=None).status_code == 200


def test_the_token_lifetime_can_be_set_per_client():
    provider = make_provider()
    provider.clients["web"].access_token_ttl = 90
    with serve(provider) as http:
        tokens = login_tokens(http)
        assert tokens["expires_in"] == 90
        assert claims_of(http, tokens["access_token"])["exp"] - int(time.time()) <= 90


def test_the_subject_is_the_user_id_or_a_stable_pairwise_value():
    with serve(make_provider(pairwise_subjects=True)) as http:
        web = claims_of(http, login_tokens(http, "web")["access_token"])["sub"]
        other = claims_of(http, login_tokens(http, "other")["access_token"])["sub"]
        again = claims_of(http, login_tokens(http, "web")["access_token"])["sub"]
        assert web == again == str(uuid.uuid5(uuid.UUID(ADA.id), "web"))
        assert web != other
        assert web != ADA.id


# -- client authentication ------------------------------------------------------------


def test_a_confidential_client_authenticates_with_basic_or_form_fields(http):
    code = get_code(http, client_id="confidential-web")
    assert redeem(http, code, client_id=None, **{}).status_code == 400  # no client at all
    response = http.post(
        "/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CALLBACK,
            "code_verifier": VERIFIER,
        },
        auth=("confidential-web", "web-secret"),
    )
    assert response.status_code == 200
    code = get_code(http, client_id="confidential-web")
    assert (
        redeem(http, code, client_id="confidential-web", client_secret="web-secret").status_code
        == 200
    )


@pytest.mark.parametrize(
    ("data", "description"),
    [
        ({"client_id": "ghost"}, "Invalid client"),
        ({"client_id": "retired"}, "Invalid client"),
        ({"client_id": "confidential-web"}, "Client authentication required"),
        ({"client_id": "confidential-web", "client_secret": "nope"}, "Invalid client credentials"),
    ],
)
def test_failed_client_authentication_is_a_401_with_a_basic_challenge(http, data, description):
    response = http.post("/oauth2/token", data={"grant_type": "authorization_code", **data})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"
    assert error(response) == ("invalid_client", description)


def test_a_missing_client_id_is_an_invalid_request(http):
    response = http.post("/oauth2/token", data={"grant_type": "authorization_code"})
    assert response.status_code == 400
    assert error(response) == ("invalid_request", "client_id is required")


def test_a_grant_the_client_may_not_use_is_unauthorized(http):
    response = http.post(
        "/oauth2/token", data={"grant_type": CLIENT_CREDENTIALS, "client_id": "web"}
    )
    assert error(response) == (
        "unauthorized_client",
        "Client is not authorized for grant_type 'client_credentials'",
    )


def test_a_grant_nobody_implements_is_unsupported(http):
    response = http.post(
        "/oauth2/token",
        data={"grant_type": "password", "client_id": "no-grants"},
        auth=("no-grants", "s"),
    )
    assert error(response)[0] == "unsupported_grant_type"


# -- refresh token --------------------------------------------------------------------


def refresh(http, token, client_id="web", **extra):
    return http.post(
        "/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token,
            "client_id": client_id,
            **extra,
        },
    )


def test_a_refresh_token_is_rotated(http):
    first = login_tokens(http)
    response = refresh(http, first["refresh_token"])
    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]
    assert second["scope"] == "openid profile email"
    assert claims_of(http, second["access_token"])["sub"] == ADA.id
    replay = refresh(http, first["refresh_token"])
    assert error(replay) == ("invalid_grant", "Invalid or expired refresh token")


def test_a_refresh_can_narrow_but_not_widen_the_scopes(http):
    tokens = login_tokens(http)
    narrowed = refresh(http, tokens["refresh_token"], scope="openid")
    assert narrowed.json()["scope"] == "openid"
    widened = refresh(http, narrowed.json()["refresh_token"], scope="openid email")
    assert error(widened) == ("invalid_scope", "Requested scopes exceed original token scopes")


@pytest.mark.parametrize(
    ("token", "client_id", "expected"),
    [
        (None, "web", ("invalid_request", "refresh_token is required")),
        ("unknown", "web", ("invalid_grant", "Invalid or expired refresh token")),
        ("OWN", "other", ("invalid_grant", "Refresh token was not issued to this client")),
    ],
)
def test_refresh_validation(http, token, client_id, expected):
    own = login_tokens(http)["refresh_token"]
    token = own if token == "OWN" else token
    data = {"grant_type": "refresh_token", "client_id": client_id}
    if token:
        data["refresh_token"] = token
    response = http.post("/oauth2/token", data=data)
    assert response.status_code == 400
    assert error(response) == expected


def test_an_expired_refresh_token_is_refused():
    provider = make_provider(refresh_token_ttl=60)
    with serve(provider) as http:
        tokens = login_tokens(http)
        provider.clock = lambda: time.time() + 61
        assert error(refresh(http, tokens["refresh_token"]))[0] == "invalid_grant"


# -- client credentials ---------------------------------------------------------------


def credentials(http, client=("service", "service-secret"), **data):
    return http.post("/oauth2/token", data={"grant_type": CLIENT_CREDENTIALS, **data}, auth=client)


def test_client_credentials_issue_a_token_without_user_or_refresh_token(http):
    response = credentials(http, scope="billing:read vpn:admin")
    assert response.status_code == 200
    body = response.json()
    assert "refresh_token" not in body
    assert body["scope"] == "billing:read vpn:admin"
    claims = claims_of(http, body["access_token"])
    assert claims["sub"] == claims["client_id"] == claims["aud"] == "service"


def test_without_a_scope_all_the_allowed_scopes_are_granted(http):
    scope = credentials(http).json()["scope"]
    assert scope.split() == ["openid", "profile", "email", "billing:*", "vpn:*", "introspect"]


def test_scopes_beyond_the_client_allowance_are_refused(http):
    response = credentials(http, client=("narrow", "narrow-secret"), scope="billing:write")
    assert error(response) == ("invalid_scope", "Requested scope exceeds client's allowed scopes")
    assert credentials(http, scope="knowledge:read").status_code == 400


def test_client_credentials_need_a_confidential_client():
    provider = make_provider()
    provider.clients["web"].grant_types = (CLIENT_CREDENTIALS,)
    with serve(provider) as http:
        response = http.post(
            "/oauth2/token", data={"grant_type": CLIENT_CREDENTIALS, "client_id": "web"}
        )
        assert error(response) == (
            "unauthorized_client",
            "client_credentials grant requires a confidential client",
        )


# -- token exchange -------------------------------------------------------------------


def user_token(http, login_hint="ada@example.test", client_id="web"):
    code = get_code(http, client_id=client_id, login_hint=login_hint)
    return redeem(http, code, client_id=client_id).json()["access_token"]


def test_an_exchange_grants_the_requested_scopes_the_user_holds(http):
    response = exchange(http, user_token(http), "billing:read vpn:admin billing:write")
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "billing:read vpn:admin"  # ada holds vpn:* but not billing:write
    assert "refresh_token" not in body
    claims = claims_of(http, body["access_token"])
    assert claims["sub"] == ADA.id
    assert claims["client_id"] == "service"
    assert claims["scope"] == "billing:read vpn:admin"


def test_an_exchange_for_scopes_the_user_lacks_is_insufficient_scope(http):
    response = exchange(http, user_token(http), "billing:write knowledge:read")
    assert response.status_code == 400
    assert error(response)[0] == "insufficient_scope"
    assert "billing:write" in error(response)[1]


def test_a_super_user_gets_everything_the_client_may_ask(http):
    token = user_token(http, "root@example.test")
    body = exchange(http, token, "billing:write vpn:admin").json()
    assert body["scope"] == "billing:write vpn:admin"


def test_the_client_allowance_bounds_the_exchange(http):
    token = user_token(http, "root@example.test")
    narrow = exchange(http, token, "billing:read vpn:admin", client=("narrow", "narrow-secret"))
    assert narrow.json()["scope"] == "billing:read"
    denied = exchange(http, token, "vpn:admin", client=("narrow", "narrow-secret"))
    assert error(denied) == ("invalid_scope", "Requested scopes not allowed for this client")


def test_without_a_scope_the_subject_scopes_are_kept(http):
    body = exchange(http, user_token(http)).json()
    assert body["scope"] == "openid profile email"


def test_scopes_already_in_the_subject_token_need_no_role(http):
    code = get_code(http, client_id="api-web", scope="openid billing:read")
    token = redeem(http, code, client_id="api-web").json()["access_token"]
    assert exchange(http, token, "billing:read").json()["scope"] == "billing:read"


def test_audience_and_actor_end_up_in_the_token(http):
    actor = credentials(http, scope="openid").json()["access_token"]
    body = exchange(
        http,
        user_token(http),
        "billing:read",
        audience="https://api.example.test",
        actor_token=actor,
        actor_token_type=ACCESS,
    ).json()
    claims = claims_of(http, body["access_token"])
    assert claims["aud"] == "https://api.example.test"
    assert claims["act"] == {"sub": "service", "client_id": "service"}


def test_the_resource_parameter_is_an_alias_of_the_audience(http):
    body = exchange(http, user_token(http), "billing:read", resource="https://res.example.test")
    assert claims_of(http, body.json()["access_token"])["aud"] == "https://res.example.test"


def test_a_jwt_subject_token_is_decoded_without_a_lookup(http):
    token = jwt.encode({"sub": ADA.id, "scope": "openid"}, "k" * 32, algorithm="HS256")
    body = exchange(http, token, "billing:read", subject_token_type=JWT_TYPE).json()
    assert body["scope"] == "billing:read"


def test_a_subject_token_without_a_user_cannot_escalate(http):
    machine = credentials(http, scope="openid billing:read").json()["access_token"]
    assert exchange(http, machine, "openid").json()["scope"] == "openid"
    refused = exchange(http, machine, "vpn:admin")
    assert error(refused) == ("invalid_scope", "Cannot escalate scopes without user identity")


def test_a_revoked_expired_or_unknown_subject_token_is_refused():
    provider = make_provider(access_token_ttl=60)
    with serve(provider) as http:
        token = user_token(http)
        jti = claims_of(http, token)["jti"]
        provider.store.access_tokens[jti].revoked = True
        assert error(exchange(http, token, "billing:read")) == (
            "invalid_request",
            "Subject token not found or revoked",
        )
        provider.store.access_tokens[jti].revoked = False
        provider.clock = lambda: time.time() + 61
        assert error(exchange(http, token, "billing:read")) == (
            "invalid_request",
            "Subject token has expired",
        )
        stranger = jwt.encode({"jti": "nope"}, "k" * 32, algorithm="HS256")
        assert error(exchange(http, stranger, "billing:read"))[1] == (
            "Subject token not found or revoked"
        )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"subject_token": None}, ("invalid_request", "subject_token is required")),
        ({"subject_token_type": None}, ("invalid_request", "subject_token_type is required")),
        (
            {"subject_token_type": "urn:x:other"},
            ("invalid_request", "Unsupported subject_token_type: urn:x:other"),
        ),
        ({"subject_token": "garbage"}, "decode"),
    ],
)
def test_exchange_parameter_validation(http, overrides, expected):
    data = {
        "grant_type": EXCHANGE,
        "subject_token": user_token(http),
        "subject_token_type": ACCESS,
    }
    data.update(overrides)
    response = http.post(
        "/oauth2/token",
        data={k: v for k, v in data.items() if v is not None},
        auth=("service", "service-secret"),
    )
    assert response.status_code == 400
    if expected == "decode":
        assert error(response)[0] == "invalid_request"
        assert error(response)[1].startswith("Failed to decode subject token")
    else:
        assert error(response) == expected


def test_an_actor_token_needs_its_type(http):
    response = exchange(http, user_token(http), "billing:read", actor_token="x.y.z")
    assert error(response) == (
        "invalid_request",
        "actor_token_type is required when actor_token is provided",
    )


def test_only_a_confidential_client_may_exchange():
    provider = make_provider()
    provider.clients["web"].grant_types = (AUTHORIZATION_CODE, TOKEN_EXCHANGE)
    with serve(provider) as http:
        token = user_token(http)
        response = http.post(
            "/oauth2/token",
            data={
                "grant_type": EXCHANGE,
                "subject_token": token,
                "subject_token_type": ACCESS,
                "client_id": "web",
            },
        )
        assert error(response) == (
            "unauthorized_client",
            "token-exchange grant requires a confidential client",
        )


def test_token_requests_are_recorded(http):
    login_tokens(http)
    record = http.provider.last_request("/oauth2/token")
    assert record.form["grant_type"] == "authorization_code"
    assert record.status == 200
    assert record.json["token_type"] == "Bearer"
