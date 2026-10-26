# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.api.clients — admin OAuth2 client endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

MODULE = "auth.api.routes.api.clients"


def _make_client(**overrides):
    """Build a mock OAuth2Client with every field the response model reads."""
    client = MagicMock()
    client.id = overrides.get("id", uuid.uuid4())
    client.client_id = overrides.get("client_id", "test_client")
    client.name = "Test App"
    client.description = None
    client.homepage_url = None
    client.redirect_uris = ["https://app.example.com/callback"]
    client.allowed_scopes = ["openid"]
    client.allowed_grant_types = ["authorization_code"]
    client.token_endpoint_auth_method = "client_secret_basic"
    client.is_confidential = overrides.get("is_confidential", True)
    client.is_active = True
    client.require_pkce = True
    client.require_consent = True
    client.jwks_uri = None
    client.allowed_origins = None
    client.access_token_expiry_seconds = None
    client.refresh_token_expiry_seconds = None
    client.tenant_id = None
    client.created_at = datetime.now(UTC)
    client.updated_at = datetime.now(UTC)
    return client


def _stamping_add():
    """Stand in for the repository add(), filling the DB-generated timestamps."""

    async def _add(_db, client):
        client.id = uuid.uuid4()
        client.created_at = datetime.now(UTC)
        client.updated_at = datetime.now(UTC)

    return AsyncMock(side_effect=_add)


def _admin():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


class TestGetClientOr404:
    @pytest.mark.asyncio
    async def test_found(self):
        from auth.api.routes.api.clients import _get_client_or_404

        client = _make_client()
        with patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=client)):
            assert await _get_client_or_404(AsyncMock(), client.id) is client

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.clients import _get_client_or_404

        with (
            patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await _get_client_or_404(AsyncMock(), uuid.uuid4())

        assert exc.value.status_code == 404


class TestCreateClient:
    def _body(self, **overrides):
        from auth.api.schemas.api.clients import CreateClientRequest

        payload = {
            "name": "My App",
            "redirect_uris": ["https://myapp.example.com/callback"],
            "allowed_grant_types": ["authorization_code"],
            "is_confidential": True,
            "require_pkce": False,
            "require_consent": True,
        }
        payload.update(overrides)
        return CreateClientRequest(**payload)

    @pytest.mark.asyncio
    async def test_confidential_client_gets_a_secret(self):
        from auth.api.routes.api.clients import create_client

        with patch(f"{MODULE}._client_service.add", _stamping_add()) as add:
            result = await create_client(self._body(), AsyncMock(), _admin())

        assert result.client_secret
        add.assert_awaited_once()
        staged = add.await_args[0][1]
        assert staged.client_secret_hash is not None

    @pytest.mark.asyncio
    async def test_public_client_gets_no_secret(self):
        from auth.api.routes.api.clients import create_client

        with patch(f"{MODULE}._client_service.add", _stamping_add()) as add:
            result = await create_client(self._body(is_confidential=False), AsyncMock(), _admin())

        assert result.client_secret is None
        assert add.await_args[0][1].client_secret_hash is None


class TestGetClient:
    @pytest.mark.asyncio
    async def test_returns_the_client(self):
        from auth.api.routes.api.clients import get_client

        client = _make_client()
        with patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=client)):
            result = await get_client(client.id, AsyncMock(), _admin())

        assert result.client_id == "test_client"

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.clients import get_client

        with (
            patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_client(uuid.uuid4(), AsyncMock(), _admin())

        assert exc.value.status_code == 404


class TestUpdateClient:
    @pytest.mark.asyncio
    async def test_only_supplied_fields_are_written(self):
        from auth.api.routes.api.clients import update_client
        from auth.api.schemas.api.clients import UpdateClientRequest

        client = _make_client()
        db = AsyncMock()

        with patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=client)):
            result = await update_client(
                client.id,
                UpdateClientRequest(name="Renamed", is_active=False),
                db,
                _admin(),
            )

        assert client.name == "Renamed"
        assert client.is_active is False
        assert result.name == "Renamed"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.clients import update_client
        from auth.api.schemas.api.clients import UpdateClientRequest

        with (
            patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await update_client(uuid.uuid4(), UpdateClientRequest(name="x"), AsyncMock(), _admin())

        assert exc.value.status_code == 404


class TestDeleteClient:
    @pytest.mark.asyncio
    async def test_delegates_to_service(self):
        from auth.api.routes.api.clients import delete_client

        client = _make_client()
        db = AsyncMock()

        with (
            patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=client)),
            patch(f"{MODULE}._client_service.delete", AsyncMock()) as delete,
        ):
            assert await delete_client(client.id, db, _admin()) is None

        delete.assert_awaited_once_with(db, client)

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.clients import delete_client

        with (
            patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await delete_client(uuid.uuid4(), AsyncMock(), _admin())

        assert exc.value.status_code == 404


class TestRotateClientSecret:
    @pytest.mark.asyncio
    async def test_confidential_client_gets_a_new_secret(self):
        from auth.api.routes.api.clients import rotate_client_secret

        client = _make_client()
        old_hash = client.client_secret_hash
        db = AsyncMock()

        with patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=client)):
            result = await rotate_client_secret(client.id, db, _admin())

        assert result.client_secret
        assert result.client_id == "test_client"
        assert client.client_secret_hash != old_hash
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_public_client_is_rejected(self):
        from auth.api.routes.api.clients import rotate_client_secret

        client = _make_client(is_confidential=False)

        with (
            patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=client)),
            pytest.raises(HTTPException) as exc,
        ):
            await rotate_client_secret(client.id, AsyncMock(), _admin())

        assert exc.value.status_code == 400
        assert "public client" in exc.value.detail

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.clients import rotate_client_secret

        with (
            patch(f"{MODULE}._client_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await rotate_client_secret(uuid.uuid4(), AsyncMock(), _admin())

        assert exc.value.status_code == 404
