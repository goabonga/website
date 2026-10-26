# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication dependencies and the ``/me`` endpoint."""

import jwt
import pytest
from apt_server.auth import AuthContext, require_scopes
from apt_server.auth.dependencies import _is_jwt_token
from apt_server.auth.introspection import TokenRevokedError, introspection_client
from apt_server.auth.token_exchange import TokenExchangeError, token_exchange_client
from apt_server.auth.userinfo import userinfo_client
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

JWT = "aaa.bbb.ccc"
USER_ID = "3f2c8f0e-1b7a-4b43-9a55-0d2f4f0e9a11"


def bearer(token: str = JWT) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def claims(monkeypatch: pytest.MonkeyPatch):
    """Make both introspection paths return the same claims."""
    data = {"sub": USER_ID, "scope": "apt:read", "client_id": "cli"}

    async def validate(token: str) -> dict:
        return data

    monkeypatch.setattr(introspection_client, "validate_token_with_introspection", validate)
    monkeypatch.setattr(introspection_client, "validate_opaque_token", validate)
    return data


@pytest.mark.parametrize(
    ("token", "expected"),
    [("a.b.c", True), ("a.b", False), ("a..c", False), ("gab_pat_123", False)],
)
def test_jwt_shape_detection(token: str, expected: bool) -> None:
    assert _is_jwt_token(token) is expected


def test_me_requires_a_token(client: TestClient, oidc_settings) -> None:
    response = client.get("/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_is_unavailable_when_oauth2_is_not_configured(client: TestClient) -> None:
    response = client.get("/me", headers=bearer())

    assert response.status_code == 503


def test_me_returns_profile(client: TestClient, oidc_settings, claims, monkeypatch) -> None:
    async def userinfo(token: str) -> dict:
        return {"email": "a@example.com", "name": "Alice", "picture": "/p.png"}

    monkeypatch.setattr(userinfo_client, "get_userinfo", userinfo)

    response = client.get("/me", headers=bearer())

    assert response.status_code == 200
    assert response.json() == {
        "user_id": USER_ID,
        "email": "a@example.com",
        "name": "Alice",
        "picture": "/p.png",
        "scopes": ["apt:read"],
    }


def test_opaque_tokens_use_opaque_validation(
    client: TestClient, oidc_settings, monkeypatch
) -> None:
    used: list[str] = []

    async def opaque(token: str) -> dict:
        used.append("opaque")
        return {"sub": "ci-bot", "client_id": "ci-bot"}

    async def userinfo(token: str) -> dict:
        return {}

    monkeypatch.setattr(introspection_client, "validate_opaque_token", opaque)
    monkeypatch.setattr(userinfo_client, "get_userinfo", userinfo)

    response = client.get("/me", headers=bearer("gab_pat_secret"))

    assert response.status_code == 200
    assert used == ["opaque"]


def test_revoked_token_is_rejected(client: TestClient, oidc_settings, monkeypatch) -> None:
    async def revoked(token: str) -> dict:
        raise TokenRevokedError("gone")

    monkeypatch.setattr(introspection_client, "validate_token_with_introspection", revoked)

    response = client.get("/me", headers=bearer())

    assert response.status_code == 401
    assert response.json()["detail"] == "Token has been revoked"


def test_invalid_token_is_rejected(client: TestClient, oidc_settings, monkeypatch) -> None:
    async def invalid(token: str) -> dict:
        raise jwt.InvalidTokenError("bad")

    monkeypatch.setattr(introspection_client, "validate_token_with_introspection", invalid)

    response = client.get("/me", headers=bearer())

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


# --- require_scopes --------------------------------------------------------


@pytest.fixture
def scoped_client(oidc_settings) -> TestClient:
    from apt_server.auth.dependencies import oauth2_scheme  # noqa: F401

    app = FastAPI()

    @app.get("/read")
    async def read(auth: AuthContext = Depends(require_scopes("apt:read"))) -> dict:
        return {"user": auth.user_id}

    @app.get("/write")
    async def write(auth: AuthContext = Depends(require_scopes("apt:write"))) -> dict:
        return {"user": auth.user_id}

    return TestClient(app)


def test_scope_granted_by_introspection(scoped_client: TestClient, claims) -> None:
    assert scoped_client.get("/read", headers=bearer("gab_pat_x")).status_code == 200


def test_missing_scope_is_forbidden(scoped_client: TestClient, claims) -> None:
    response = scoped_client.get("/write", headers=bearer("gab_pat_x"))

    assert response.status_code == 403
    assert "apt:write" in response.json()["detail"]
    assert 'error="insufficient_scope"' in response.headers["WWW-Authenticate"]


def test_wildcard_scope_satisfies_requirement(scoped_client: TestClient, claims) -> None:
    claims["scope"] = "apt:*"

    assert scoped_client.get("/write", headers=bearer("gab_pat_x")).status_code == 200


def test_scoped_route_requires_token(scoped_client: TestClient) -> None:
    assert scoped_client.get("/read").status_code == 401


@pytest.fixture
def exchange(monkeypatch: pytest.MonkeyPatch):
    """Enable token exchange and let tests choose its outcome."""
    outcome: dict = {"result": {"scope": "apt:write", "claims": {"sub": USER_ID}}}

    async def validate(token: str, scopes: list[str]) -> dict:
        result = outcome["result"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(token_exchange_client, "validate_token_scopes", validate)
    return outcome


def test_jwt_scopes_come_from_token_exchange(scoped_client: TestClient, exchange) -> None:
    response = scoped_client.get("/write", headers=bearer())

    assert response.status_code == 200
    assert response.json() == {"user": USER_ID}


def test_exchange_without_claims_falls_back_to_introspection(
    scoped_client: TestClient, exchange, claims
) -> None:
    exchange["result"] = {"scope": "apt:write"}

    assert scoped_client.get("/write", headers=bearer()).status_code == 200


@pytest.mark.parametrize(
    ("code", "status"),
    [("invalid_grant", 401), ("insufficient_scope", 403), ("server_error", 401)],
)
def test_exchange_errors_map_to_http_status(
    scoped_client: TestClient, exchange, code: str, status: int
) -> None:
    exchange["result"] = TokenExchangeError("failed", error_code=code)

    assert scoped_client.get("/write", headers=bearer()).status_code == status
