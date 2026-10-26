# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/routes/access.py: the client registry is checked on every call."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.auth import AuthContext
from custom_domain.auth.models import User
from custom_domain.main import app
from custom_domain.routes.access import ensure_client_authorized
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


def make_auth(client_id="tenant-a", scopes=("custom-domain:read",)):
    return AuthContext(user=User(id=uuid4(), scopes=list(scopes), client_id=client_id))


class TestEnsureClientAuthorized:
    """Unit tests of the registry check."""

    @pytest.mark.asyncio
    async def test_active_client_passes(self):
        with patch("custom_domain.routes.access.domain_service") as service:
            service.get_authorized_client = AsyncMock(return_value=MagicMock())
            await ensure_client_authorized(AsyncMock(), make_auth())
        service.get_authorized_client.assert_awaited_once()
        assert service.get_authorized_client.await_args.args[1] == "tenant-a"

    @pytest.mark.asyncio
    async def test_unknown_or_inactive_client_is_refused(self):
        with patch("custom_domain.routes.access.domain_service") as service:
            service.get_authorized_client = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await ensure_client_authorized(AsyncMock(), make_auth())
        assert exc.value.status_code == 403
        assert exc.value.detail == "Client not authorized"

    @pytest.mark.asyncio
    async def test_token_without_client_is_refused(self):
        with patch("custom_domain.routes.access.domain_service") as service:
            service.get_authorized_client = AsyncMock()
            with pytest.raises(HTTPException) as exc:
                await ensure_client_authorized(AsyncMock(), make_auth(client_id=None))
        assert exc.value.status_code == 403
        assert exc.value.detail == "Client ID required"
        service.get_authorized_client.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_administrator_is_not_checked(self):
        admin = make_auth(client_id=None, scopes=("custom-domain:admin",))
        with patch("custom_domain.routes.access.domain_service") as service:
            service.get_authorized_client = AsyncMock()
            await ensure_client_authorized(AsyncMock(), admin)
        service.get_authorized_client.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_administration_scope_is_configurable(self, monkeypatch):
        from custom_domain.config import settings

        monkeypatch.setattr(settings, "admin_scope", "ops:root")
        with patch("custom_domain.routes.access.domain_service") as service:
            service.get_authorized_client = AsyncMock(return_value=None)
            await ensure_client_authorized(
                AsyncMock(), make_auth(client_id=None, scopes=("ops:root",))
            )
            with pytest.raises(HTTPException):
                await ensure_client_authorized(
                    AsyncMock(), make_auth(scopes=("custom-domain:admin",))
                )


DOMAIN_ID = "00000000-0000-0000-0000-000000000001"

ENDPOINTS = [
    ("GET", "/api/v1/domains", "custom-domain:read"),
    ("POST", "/api/v1/domains", "custom-domain:write"),
    ("GET", f"/api/v1/domains/{DOMAIN_ID}", "custom-domain:read"),
    ("PUT", f"/api/v1/domains/{DOMAIN_ID}", "custom-domain:write"),
    ("DELETE", f"/api/v1/domains/{DOMAIN_ID}", "custom-domain:write"),
    ("GET", "/api/v1/domains/lookup/shop.example.com", "custom-domain:lookup"),
    ("POST", f"/api/v1/domains/{DOMAIN_ID}/verify", "custom-domain:write"),
    ("POST", f"/api/v1/domains/{DOMAIN_ID}/provision", "custom-domain:write"),
]


@pytest.fixture
def deactivated_client(mock_db_session):
    """An authenticated caller whose client is known to be deactivated."""
    from custom_domain.database import get_db

    from tests.conftest import _setup_auth_mocks

    user = User(
        id=uuid4(),
        scopes=["custom-domain:read", "custom-domain:write", "custom-domain:lookup"],
        client_id="tenant-a",
    )

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    patchers = _setup_auth_mocks(user)
    # the helper installs a registry that answers "active"; make it answer "unknown"
    from custom_domain.routes import access

    access.domain_service.get_authorized_client = AsyncMock(return_value=None)
    yield user
    for patcher in patchers:
        patcher.stop()
    app.dependency_overrides.clear()


class TestEveryEndpointChecksTheRegistry:
    """A deactivated client is refused on every domain endpoint, not only on creation."""

    @pytest.mark.parametrize(("method", "path", "scope"), ENDPOINTS)
    @pytest.mark.asyncio
    async def test_inactive_client_gets_403(self, deactivated_client, method, path, scope):
        body = {"json": {"domain": "x.example.com", "owner_id": "o"}} if method == "POST" else {}
        if method == "PUT":
            body = {"json": {}}
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as http:
            response = await http.request(method, path, **body)
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "Client not authorized"
