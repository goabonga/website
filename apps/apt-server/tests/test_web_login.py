# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authorization Code + PKCE login for the browser UI."""

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from apt_server.auth.introspection import TokenRevokedError, introspection_client
from apt_server.config import settings
from apt_server.db.models import UserCache
from apt_server.services import apt_auth, session
from fastapi import FastAPI
from fastapi.testclient import TestClient

ISSUER = "https://issuer.example"
REAL_ASYNC_CLIENT = httpx.AsyncClient


def unsigned_jwt(claims: dict) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part(claims)}."


@pytest.fixture(autouse=True)
def web_settings(oidc_settings, monkeypatch):
    monkeypatch.setattr(settings, "session_secret", "s3cret")
    monkeypatch.setattr(settings, "oauth2_swagger_client_id", "web-client")
    monkeypatch.setattr(settings, "session_cookie_name", "apt_session")


@pytest.fixture
def identity_provider(monkeypatch):
    """Fake token and userinfo endpoints behind ``httpx.AsyncClient``."""
    state = {
        "token_status": 200,
        "token_body": {"access_token": unsigned_jwt({"sub": "user-1"})},
        "userinfo_status": 200,
        "userinfo_body": {"email": "alice@example.com", "nickname": "Alice", "picture": "/a.png"},
        "requests": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(state["token_status"], json=state["token_body"])
        if request.url.path.endswith("/userinfo"):
            if state["userinfo_status"] == 0:
                raise httpx.ConnectError("down")
            return httpx.Response(state["userinfo_status"], json=state["userinfo_body"])
        return httpx.Response(404)

    monkeypatch.setattr(
        "apt_server.routes.auth.httpx.AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    return state


async def start_login(http) -> tuple[str, dict[str, str]]:
    response = await http.get("/login")
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0], {"Cookie": f"oauth_state={response.cookies['oauth_state']}"}


async def test_login_requires_oauth2_configuration(http, monkeypatch) -> None:
    monkeypatch.setattr(settings, "oauth2_issuer", "")

    assert (await http.get("/login")).status_code == 503


async def test_login_redirects_to_the_authorization_endpoint(http) -> None:
    response = await http.get("/login")

    assert response.status_code == 307
    target = urlparse(response.headers["location"])
    query = parse_qs(target.query)
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{ISSUER}/oauth2/authorize"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["web-client"]
    assert query["scope"] == ["openid profile email"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://test/callback"]
    cookie = session.read_state_cookie(response.cookies["oauth_state"])
    assert cookie[0] == query["state"][0]
    assert "HttpOnly" in response.headers["set-cookie"]


async def test_login_forces_https_callback_behind_a_proxy(http) -> None:
    response = await http.get("/login", headers={"x-forwarded-proto": "https"})

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["redirect_uri"] == ["https://test/callback"]


async def test_login_falls_back_to_the_confidential_client_id(http, monkeypatch) -> None:
    monkeypatch.setattr(settings, "oauth2_swagger_client_id", "")

    query = parse_qs(urlparse((await http.get("/login")).headers["location"]).query)

    assert query["client_id"] == ["apt-client"]


async def test_callback_without_state_cookie_is_rejected(http) -> None:
    response = await http.get("/callback", params={"code": "c", "state": "s"})

    assert response.status_code == 400
    assert response.json()["detail"] == "missing state cookie"


async def test_callback_with_wrong_state_is_rejected(http) -> None:
    _, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": "other"}, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid state"


async def test_callback_creates_the_session_and_caches_the_user(
    http, identity_provider, db
) -> None:
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    data = session.read_session_cookie(response.cookies["apt_session"])
    assert data.display_name == "alice@example.com"
    assert data.name == "Alice"
    assert data.avatar_url == f"{ISSUER}/a.png"
    token_request = identity_provider["requests"][0]
    assert b"code_verifier" in token_request.content and b"code=c" in token_request.content
    cached = await db.get(UserCache, "user-1")
    assert cached.email == "alice@example.com"


async def test_callback_deletes_the_state_cookie(http, identity_provider) -> None:
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    set_cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("oauth_state=") and "Max-Age=0" in c for c in set_cookies)


async def test_callback_uses_a_gravatar_without_picture(http, identity_provider) -> None:
    identity_provider["userinfo_body"] = {"email": "Alice@Example.com"}
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    data = session.read_session_cookie(response.cookies["apt_session"])
    assert data.avatar_url.startswith("https://www.gravatar.com/avatar/")


async def test_callback_keeps_absolute_picture_urls(http, identity_provider) -> None:
    identity_provider["userinfo_body"] = {"email": "a@example.com", "picture": "https://cdn/x.png"}
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    assert session.read_session_cookie(response.cookies["apt_session"]).avatar_url == (
        "https://cdn/x.png"
    )


async def test_callback_survives_a_userinfo_failure(http, identity_provider, db) -> None:
    identity_provider["userinfo_status"] = 0
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    assert response.status_code == 302
    assert session.read_session_cookie(response.cookies["apt_session"]).display_name == ""
    assert await db.get(UserCache, "user-1") is None


async def test_callback_survives_an_undecodable_access_token(http, identity_provider) -> None:
    identity_provider["token_body"] = {"access_token": "opaque-token"}
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    assert response.status_code == 302


async def test_callback_reports_a_failed_code_exchange(http, identity_provider) -> None:
    identity_provider["token_status"] = 400
    identity_provider["token_body"] = {"error": "invalid_grant"}
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    assert response.status_code == 502
    assert "token exchange failed" in response.json()["detail"]


async def test_callback_requires_an_access_token(http, identity_provider) -> None:
    identity_provider["token_body"] = {}
    state, headers = await start_login(http)

    response = await http.get("/callback", params={"code": "c", "state": state}, headers=headers)

    assert response.status_code == 502


async def test_logout_clears_the_session_cookie(http) -> None:
    response = await http.get("/logout")

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert "apt_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


# --- session cookies as credentials for apt clients and the API ------------


@pytest.fixture
def whoami() -> TestClient:
    app = FastAPI()

    @app.get("/who")
    async def who(caller: apt_auth.Caller_) -> dict:
        if caller is None:
            return {"caller": None}
        return {
            "sub": caller.sub,
            "display_name": caller.display_name,
            "name": caller.name,
            "avatar_url": caller.avatar_url,
            "is_session": caller.is_session,
        }

    return TestClient(app)


@pytest.fixture
def session_cookie() -> dict[str, str]:
    value = session.create_session_cookie(
        "tok", display_name="alice@example.com", name="Alice", avatar_url="/a.png"
    )
    return {"Cookie": f"apt_session={value}"}


def test_session_cookie_authenticates_the_caller(whoami, session_cookie, monkeypatch) -> None:
    async def validate(token: str) -> dict:
        return {"sub": "user-1", "scope": "apt:read"}

    monkeypatch.setattr(introspection_client, "validate_opaque_token", validate)

    body = whoami.get("/who", headers=session_cookie).json()

    assert body == {
        "sub": "user-1",
        "display_name": "alice@example.com",
        "name": "Alice",
        "avatar_url": "/a.png",
        "is_session": True,
    }


def test_authorization_header_wins_over_the_cookie(whoami, session_cookie, monkeypatch) -> None:
    async def validate(token: str) -> dict:
        return {"sub": f"from-{token}"}

    monkeypatch.setattr(introspection_client, "validate_opaque_token", validate)

    body = whoami.get("/who", headers={**session_cookie, "Authorization": "Bearer hdr"}).json()

    assert body["sub"] == "from-hdr"
    assert body["is_session"] is False


@pytest.mark.parametrize("failure", [TokenRevokedError("gone"), RuntimeError("boom")])
def test_dead_sessions_fall_back_to_anonymous(whoami, session_cookie, monkeypatch, failure) -> None:
    async def validate(token: str) -> dict:
        raise failure

    monkeypatch.setattr(introspection_client, "validate_opaque_token", validate)

    assert whoami.get("/who", headers=session_cookie).json() == {"caller": None}


def test_invalid_cookie_means_anonymous(whoami) -> None:
    assert whoami.get("/who", headers={"Cookie": "apt_session=forged"}).json() == {"caller": None}
