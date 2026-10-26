# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/jwks admin endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from auth.main import app as fastapi_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def _make_app():
    def factory(scopes: list[str]):
        admin_user = MagicMock()
        admin_user.id = uuid.uuid4()
        admin_user.is_active = True

        async def override_auth():
            return admin_user

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        return fastapi_app, admin_user, scopes

    yield factory
    fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_jwks_unauthenticated():
    """GET /api/v1/jwks/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/jwks/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_jwks_forbidden(_make_app):
    """GET /api/v1/jwks/ without jwks:read returns 403."""
    app, _, _ = _make_app(["users:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/jwks/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_generate_key_unauthenticated():
    """POST /api/v1/jwks/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/jwks/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_key_forbidden(_make_app):
    """POST /api/v1/jwks/ without jwks:write returns 403."""
    app, _, _ = _make_app(["jwks:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/jwks/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_key_unauthenticated():
    """GET /api/v1/jwks/{kid} without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/jwks/some-kid")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_key_forbidden(_make_app):
    """GET /api/v1/jwks/{kid} without jwks:read returns 403."""
    app, _, _ = _make_app(["users:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/jwks/some-kid")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_activate_key_unauthenticated():
    """POST /api/v1/jwks/{kid}/activate without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/jwks/some-kid/activate")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_activate_key_forbidden(_make_app):
    """POST /api/v1/jwks/{kid}/activate without jwks:write returns 403."""
    app, _, _ = _make_app(["jwks:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/jwks/some-kid/activate")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_revoke_key_unauthenticated():
    """POST /api/v1/jwks/{kid}/revoke without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/jwks/some-kid/revoke")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoke_key_forbidden(_make_app):
    """POST /api/v1/jwks/{kid}/revoke without jwks:revoke returns 403."""
    app, _, _ = _make_app(["jwks:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/jwks/some-kid/revoke")
    assert response.status_code == 403


def _make_mock_jwk(is_active: bool = False) -> MagicMock:
    """Build a MagicMock JWK suitable for JWKResponse.model_validate."""
    mock_jwk = MagicMock()
    mock_jwk.id = uuid.uuid4()
    mock_jwk.kid = str(uuid.uuid4())
    mock_jwk.kty = "RSA"
    mock_jwk.alg = "RS256"
    mock_jwk.use = "sig"
    mock_jwk.is_active = is_active
    mock_jwk.revoked_at = None
    mock_jwk.created_at = datetime.now(UTC)
    return mock_jwk


@pytest.mark.asyncio
async def test_generate_key_with_custom_key_size(_make_app):
    """POST /api/v1/jwks/ with key_size=4096 forwards the param to the service."""
    app, _, _ = _make_app(["jwks:write"])

    mock_jwk = _make_mock_jwk(is_active=False)
    mock_service = MagicMock()
    mock_service.generate_key = AsyncMock(return_value=mock_jwk)

    from auth.api.deps import get_jwks_service

    app.dependency_overrides[get_jwks_service] = lambda: mock_service

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/jwks/",
                json={"key_size": 4096, "activate": False},
            )

    assert response.status_code == 201
    mock_service.generate_key.assert_awaited_once()
    call_kwargs = mock_service.generate_key.await_args.kwargs
    assert call_kwargs["key_size"] == 4096
    assert call_kwargs["activate"] is False


@pytest.mark.asyncio
async def test_generate_key_with_activate_true(_make_app):
    """POST /api/v1/jwks/ with activate=true creates and activates the key."""
    app, _, _ = _make_app(["jwks:write"])

    mock_jwk = _make_mock_jwk(is_active=True)
    mock_service = MagicMock()
    mock_service.generate_key = AsyncMock(return_value=mock_jwk)

    from auth.api.deps import get_jwks_service

    app.dependency_overrides[get_jwks_service] = lambda: mock_service

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/jwks/",
                json={"key_size": 3072, "activate": True},
            )

    assert response.status_code == 201
    data = response.json()
    assert data["is_active"] is True
    mock_service.generate_key.assert_awaited_once()
    call_kwargs = mock_service.generate_key.await_args.kwargs
    assert call_kwargs["key_size"] == 3072
    assert call_kwargs["activate"] is True


@pytest.mark.asyncio
async def test_generate_key_defaults_without_body(_make_app):
    """POST /api/v1/jwks/ without body uses service defaults (key_size=2048, activate=False)."""
    app, _, _ = _make_app(["jwks:write"])

    mock_jwk = _make_mock_jwk(is_active=False)
    mock_service = MagicMock()
    mock_service.generate_key = AsyncMock(return_value=mock_jwk)

    from auth.api.deps import get_jwks_service

    app.dependency_overrides[get_jwks_service] = lambda: mock_service

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/jwks/")

    assert response.status_code == 201
    mock_service.generate_key.assert_awaited_once()
    call_kwargs = mock_service.generate_key.await_args.kwargs
    assert call_kwargs["key_size"] == 2048
    assert call_kwargs["activate"] is False


@pytest.mark.asyncio
async def test_generate_key_invalid_key_size_rejected(_make_app):
    """POST /api/v1/jwks/ with invalid key_size returns 422 and does not call the service."""
    app, _, _ = _make_app(["jwks:write"])

    mock_service = MagicMock()
    mock_service.generate_key = AsyncMock()

    from auth.api.deps import get_jwks_service

    app.dependency_overrides[get_jwks_service] = lambda: mock_service

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/jwks/", json={"key_size": 1024})

    assert response.status_code == 422
    mock_service.generate_key.assert_not_awaited()


@pytest.mark.asyncio
async def test_rotate_keys_with_custom_key_size(_make_app):
    """POST /api/v1/jwks/rotate with key_size=4096 forwards the param to the service."""
    app, _, _ = _make_app(["jwks:rotate"])

    mock_jwk = _make_mock_jwk(is_active=True)
    mock_service = MagicMock()
    mock_service.rotate_keys = AsyncMock(return_value=mock_jwk)

    from auth.api.deps import get_jwks_service

    app.dependency_overrides[get_jwks_service] = lambda: mock_service

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/jwks/rotate", json={"key_size": 4096})

    assert response.status_code == 200
    mock_service.rotate_keys.assert_awaited_once()
    call_kwargs = mock_service.rotate_keys.await_args.kwargs
    assert call_kwargs["key_size"] == 4096


@pytest.mark.asyncio
async def test_rotate_keys_invalid_key_size_rejected(_make_app):
    """POST /api/v1/jwks/rotate with invalid key_size returns 422."""
    app, _, _ = _make_app(["jwks:rotate"])

    mock_service = MagicMock()
    mock_service.rotate_keys = AsyncMock()

    from auth.api.deps import get_jwks_service

    app.dependency_overrides[get_jwks_service] = lambda: mock_service

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/jwks/rotate", json={"key_size": 512})

    assert response.status_code == 422
    mock_service.rotate_keys.assert_not_awaited()
