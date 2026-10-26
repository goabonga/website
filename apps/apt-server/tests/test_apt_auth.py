# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Credential resolution for apt clients: anonymous, Basic or Bearer."""

import base64

import jwt
import pytest
from apt_server.auth.introspection import TokenRevokedError, introspection_client
from apt_server.services import apt_auth
from fastapi import FastAPI
from fastapi.testclient import TestClient


def basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def test_extract_basic_credentials() -> None:
    assert apt_auth._extract_credentials(basic("alice@example.com", "gab_pat_x")) == (
        "alice@example.com",
        "gab_pat_x",
    )


def test_extract_basic_credentials_keeps_colons_in_the_password() -> None:
    assert apt_auth._extract_credentials(basic("alice", "a:b")) == ("alice", "a:b")


def test_extract_basic_with_empty_username_or_password() -> None:
    assert apt_auth._extract_credentials(basic("", "secret")) == (None, "secret")
    assert apt_auth._extract_credentials(basic("alice", "")) == ("alice", None)


def test_extract_bearer_credentials() -> None:
    assert apt_auth._extract_credentials("Bearer gab_pat_x") == (None, "gab_pat_x")


@pytest.mark.parametrize("header", [None, "", "Bearer", "Digest abc", "Basic !!!not-base64"])
def test_extract_ignores_missing_or_unsupported_headers(header) -> None:
    assert apt_auth._extract_credentials(header) == (None, None)


def test_basic_realm_advertises_utf8() -> None:
    assert apt_auth.BASIC_REALM == 'Basic realm="apt", charset="UTF-8"'


@pytest.fixture
def whoami(oidc_settings) -> TestClient:
    """Tiny app echoing the resolved caller."""
    app = FastAPI()

    @app.get("/who")
    async def who(caller: apt_auth.Caller_) -> dict:
        if caller is None:
            return {"caller": None}
        return {
            "sub": caller.sub,
            "scopes": sorted(caller.scopes),
            "groups": sorted(caller.groups),
            "display_name": caller.display_name,
            "name": caller.name,
        }

    return TestClient(app)


@pytest.fixture
def introspected(monkeypatch: pytest.MonkeyPatch) -> dict:
    claims: dict = {
        "sub": "user-1",
        "scope": "apt:read apt:write",
        "email": "alice@example.com",
        "name": "Alice",
        "groups": ["team:ops"],
    }

    async def validate(token: str) -> dict:
        return claims

    monkeypatch.setattr(introspection_client, "validate_opaque_token", validate)
    monkeypatch.setattr(introspection_client, "validate_token_with_introspection", validate)
    return claims


def test_no_credentials_means_anonymous(whoami: TestClient) -> None:
    assert whoami.get("/who").json() == {"caller": None}


def test_basic_auth_with_a_personal_access_token(whoami: TestClient, introspected) -> None:
    response = whoami.get("/who", headers={"Authorization": basic("alice", "gab_pat_x")})

    assert response.json() == {
        "sub": "user-1",
        "scopes": ["apt:read", "apt:write"],
        "groups": ["team:ops"],
        "display_name": "alice@example.com",
        "name": "Alice",
    }


def test_bearer_jwt_is_validated_with_signature_check(
    whoami: TestClient, introspected, monkeypatch
):
    used: list[str] = []

    async def validate(token: str) -> dict:
        used.append(token)
        return introspected

    monkeypatch.setattr(introspection_client, "validate_token_with_introspection", validate)

    response = whoami.get("/who", headers={"Authorization": "Bearer aaa.bbb.ccc"})

    assert response.json()["sub"] == "user-1"
    assert used == ["aaa.bbb.ccc"]


def test_groups_claim_can_be_a_string_and_scopes_a_list(whoami: TestClient, introspected) -> None:
    introspected.update({"groups": "a b", "scope": None, "scopes": ["apt:read"]})

    body = whoami.get("/who", headers={"Authorization": "Bearer gab_pat_x"}).json()

    assert body["groups"] == ["a", "b"]
    assert body["scopes"] == ["apt:read"]


def test_display_name_falls_back_to_the_subject(whoami: TestClient, introspected) -> None:
    introspected.pop("email")
    introspected.pop("name")

    body = whoami.get("/who", headers={"Authorization": "Bearer gab_pat_x"}).json()

    assert body["display_name"] == "user-1"


def test_revoked_credentials_get_a_basic_challenge(whoami: TestClient, monkeypatch) -> None:
    async def revoked(token: str) -> dict:
        raise TokenRevokedError("gone")

    monkeypatch.setattr(introspection_client, "validate_opaque_token", revoked)

    response = whoami.get("/who", headers={"Authorization": basic("alice", "gab_pat_x")})

    assert response.status_code == 401
    assert response.json()["detail"] == "token revoked"
    assert response.headers["WWW-Authenticate"] == apt_auth.BASIC_REALM


def test_invalid_credentials_get_a_basic_challenge(whoami: TestClient, monkeypatch) -> None:
    async def invalid(token: str) -> dict:
        raise jwt.InvalidTokenError("bad")

    monkeypatch.setattr(introspection_client, "validate_opaque_token", invalid)

    response = whoami.get("/who", headers={"Authorization": "Bearer gab_pat_x"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid credentials"


def test_token_without_subject_is_rejected(whoami: TestClient, introspected) -> None:
    introspected.pop("sub")

    response = whoami.get("/who", headers={"Authorization": "Bearer gab_pat_x"})

    assert response.status_code == 401
    assert response.json()["detail"] == "token has no subject"


def test_credentials_without_oauth2_configuration_are_unavailable(whoami: TestClient, monkeypatch):
    from apt_server.config import settings

    monkeypatch.setattr(settings, "oauth2_issuer", "")

    response = whoami.get("/who", headers={"Authorization": "Bearer gab_pat_x"})

    assert response.status_code == 503
