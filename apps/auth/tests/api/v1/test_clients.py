# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/clients admin endpoints."""

import uuid
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
async def test_list_clients_unauthenticated():
    """GET /api/v1/clients/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/clients/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_clients_forbidden(_make_app):
    """GET /api/v1/clients/ without clients:read returns 403."""
    app, _, _ = _make_app(["users:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/clients/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_clients_success(_make_app):
    """GET /api/v1/clients/ returns paginated clients."""
    app, _, _ = _make_app(["clients:read"])

    mock_client = MagicMock()
    mock_client.id = uuid.uuid4()
    mock_client.client_id = "test_client"
    mock_client.name = "Test App"
    mock_client.is_confidential = True
    mock_client.require_pkce = True
    mock_client.is_active = True
    mock_client.tenant_id = None
    mock_client.redirect_uris = ["https://app.example.com/callback"]
    mock_client.allowed_scopes = ["openid"]
    mock_client.allowed_grant_types = ["authorization_code"]
    mock_client.description = None
    mock_client.homepage_url = None
    mock_client.require_consent = True
    mock_client.token_endpoint_auth_method = "client_secret_basic"
    mock_client.jwks_uri = None
    mock_client.allowed_origins = None
    mock_client.access_token_expiry_seconds = None
    mock_client.refresh_token_expiry_seconds = None
    mock_client.created_at = MagicMock()
    mock_client.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    mock_client.updated_at = MagicMock()
    mock_client.updated_at.isoformat.return_value = "2024-01-01T00:00:00"

    mock_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    list_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [mock_client]
    list_result.scalars.return_value = scalars
    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/clients/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
