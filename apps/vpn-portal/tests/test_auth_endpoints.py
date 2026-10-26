# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""End-to-end tests of the auth dependencies on a minimal application.

The application protects two routes with ``require_scopes`` and ``get_auth_context``.
Only the network-facing collaborators (JWKS, introspection, token exchange) are replaced.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from vpn_portal.auth import AuthContext, get_auth_context, require_scopes
from vpn_portal.auth.introspection import TokenRevokedError
from vpn_portal.auth.token_exchange import TokenExchangeError

JWT = "header.payload.signature"
OPAQUE = "opaque-personal-access-token"


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(auth: AuthContext = Depends(get_auth_context)):
        return {"user_id": auth.user_id, "scopes": auth.scopes}

    @app.get("/connect")
    async def connect(auth: AuthContext = Depends(require_scopes("vpn:connect"))):
        return {"user_id": auth.user_id, "scopes": auth.scopes}

    return app


def claims(scope: str, **extra) -> dict:
    return {"sub": str(uuid4()), "email": "u@example.com", "scope": scope, **extra}


@pytest.fixture
def collaborators():
    with (
        patch("vpn_portal.auth.dependencies.jwks_manager") as jwks,
        patch("vpn_portal.auth.dependencies.introspection_client") as introspection,
        patch("vpn_portal.auth.dependencies.token_exchange_client") as exchange,
    ):
        jwks.is_configured = True
        exchange.is_configured = False
        introspection.validate_token_with_introspection = AsyncMock()
        introspection.validate_opaque_token = AsyncMock()
        exchange.validate_token_scopes = AsyncMock()
        yield jwks, introspection, exchange


async def get(path: str, token: str | None = JWT):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test", headers=headers
    ) as client:
        return await client.get(path)


async def test_missing_token_is_rejected(collaborators):
    response = await get("/connect", token=None)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_unconfigured_oauth2_is_503(collaborators):
    collaborators[0].is_configured = False

    assert (await get("/connect")).status_code == 503


async def test_jwt_with_required_scope_is_accepted(collaborators):
    _, introspection, _ = collaborators
    introspection.validate_token_with_introspection.return_value = claims("vpn:connect openid")

    response = await get("/connect")

    assert response.status_code == 200
    assert response.json()["scopes"] == ["vpn:connect", "openid"]


async def test_jwt_without_required_scope_is_403(collaborators):
    _, introspection, _ = collaborators
    introspection.validate_token_with_introspection.return_value = claims("openid")

    response = await get("/connect")

    assert response.status_code == 403
    assert "vpn:connect" in response.json()["detail"]
    assert "insufficient_scope" in response.headers["www-authenticate"]


async def test_wildcard_scope_grants_access(collaborators):
    _, introspection, _ = collaborators
    introspection.validate_token_with_introspection.return_value = claims("vpn:*")

    assert (await get("/connect")).status_code == 200


async def test_invalid_token_is_401(collaborators):
    _, introspection, _ = collaborators
    introspection.validate_token_with_introspection.side_effect = ValueError("bad signature")

    response = await get("/connect")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


async def test_revoked_token_is_401(collaborators):
    _, introspection, _ = collaborators
    introspection.validate_token_with_introspection.side_effect = TokenRevokedError("revoked")

    response = await get("/connect")

    assert response.status_code == 401
    assert response.json()["detail"] == "Token has been revoked"


async def test_opaque_token_uses_introspection_only(collaborators):
    _, introspection, _ = collaborators
    introspection.validate_opaque_token.return_value = claims("vpn:connect")

    response = await get("/connect", token=OPAQUE)

    assert response.status_code == 200
    introspection.validate_opaque_token.assert_awaited_once_with(OPAQUE)
    introspection.validate_token_with_introspection.assert_not_called()


async def test_token_exchange_grants_scopes(collaborators):
    _, introspection, exchange = collaborators
    exchange.is_configured = True
    exchange.validate_token_scopes.return_value = {
        "scope": "vpn:connect",
        "claims": claims("openid"),
    }

    response = await get("/connect")

    assert response.status_code == 200
    assert response.json()["scopes"] == ["vpn:connect"]
    exchange.validate_token_scopes.assert_awaited_once_with(JWT, ["vpn:connect"])


async def test_token_exchange_insufficient_scope_is_403(collaborators):
    _, _, exchange = collaborators
    exchange.is_configured = True
    exchange.validate_token_scopes.side_effect = TokenExchangeError(
        "insufficient_scope: no", error_code="insufficient_scope"
    )

    response = await get("/connect")

    assert response.status_code == 403


async def test_token_exchange_invalid_grant_is_401(collaborators):
    _, _, exchange = collaborators
    exchange.is_configured = True
    exchange.validate_token_scopes.side_effect = TokenExchangeError(
        "invalid_grant: expired", error_code="invalid_grant"
    )

    assert (await get("/connect")).status_code == 401


async def test_get_auth_context_returns_the_user(collaborators):
    _, introspection, _ = collaborators
    introspection.validate_token_with_introspection.return_value = claims("openid profile")

    response = await get("/whoami")

    assert response.status_code == 200
    assert response.json()["scopes"] == ["openid", "profile"]
