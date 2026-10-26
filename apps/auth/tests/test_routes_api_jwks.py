# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.api.jwks — admin JWK management endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


def _make_jwk(kid="kid-1"):
    """Build a mock JWK row with the fields JWKResponse reads."""
    jwk = MagicMock()
    jwk.id = uuid.uuid4()
    jwk.kid = kid
    jwk.kty = "RSA"
    jwk.alg = "RS256"
    jwk.use = "sig"
    jwk.key_size = 2048
    jwk.is_active = True
    jwk.revoked_at = None
    jwk.created_at = datetime.now(UTC)
    jwk.expires_at = None
    return jwk


def _admin():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


class TestListKeys:
    @pytest.mark.asyncio
    async def test_excludes_revoked_keys(self):
        from auth.api.routes.api.jwks import list_keys

        jwks_service = AsyncMock()
        jwks_service.list = AsyncMock(return_value=[_make_jwk()])
        db = AsyncMock()

        result = await list_keys(db, _admin(), jwks_service)

        assert len(result) == 1
        jwks_service.list.assert_awaited_once_with(db, include_revoked=False)


class TestGetKey:
    @pytest.mark.asyncio
    async def test_found(self):
        from auth.api.routes.api.jwks import get_key

        jwks_service = AsyncMock()
        jwks_service.get_by_kid = AsyncMock(return_value=_make_jwk())

        result = await get_key("kid-1", AsyncMock(), _admin(), jwks_service)

        assert result.kid == "kid-1"

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.jwks import get_key

        jwks_service = AsyncMock()
        jwks_service.get_by_kid = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await get_key("nope", AsyncMock(), _admin(), jwks_service)

        assert exc.value.status_code == 404


class TestActivateKey:
    @pytest.mark.asyncio
    async def test_success(self):
        from auth.api.routes.api.jwks import activate_key

        jwks_service = AsyncMock()
        jwks_service.activate_key = AsyncMock(return_value=_make_jwk())

        result = await activate_key("kid-1", AsyncMock(), _admin(), jwks_service)

        assert result.kid == "kid-1"

    @pytest.mark.asyncio
    async def test_value_error_becomes_400(self):
        from auth.api.routes.api.jwks import activate_key

        jwks_service = AsyncMock()
        jwks_service.activate_key = AsyncMock(side_effect=ValueError("key is revoked"))

        with pytest.raises(HTTPException) as exc:
            await activate_key("kid-1", AsyncMock(), _admin(), jwks_service)

        assert exc.value.status_code == 400
        assert exc.value.detail == "key is revoked"

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.jwks import activate_key

        jwks_service = AsyncMock()
        jwks_service.activate_key = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await activate_key("nope", AsyncMock(), _admin(), jwks_service)

        assert exc.value.status_code == 404


class TestRevokeKey:
    @pytest.mark.asyncio
    async def test_success(self):
        from auth.api.routes.api.jwks import revoke_key

        jwks_service = AsyncMock()
        jwks_service.revoke_key = AsyncMock(return_value=_make_jwk())

        result = await revoke_key("kid-1", AsyncMock(), _admin(), jwks_service)

        assert result.kid == "kid-1"

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.jwks import revoke_key

        jwks_service = AsyncMock()
        jwks_service.revoke_key = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await revoke_key("nope", AsyncMock(), _admin(), jwks_service)

        assert exc.value.status_code == 404


class TestDeleteKey:
    @pytest.mark.asyncio
    async def test_success_returns_204(self):
        from auth.api.routes.api.jwks import delete_key

        jwks_service = AsyncMock()
        jwks_service.delete = AsyncMock(return_value=True)

        result = await delete_key("kid-1", AsyncMock(), _admin(), jwks_service)

        assert result.status_code == 204

    @pytest.mark.asyncio
    async def test_unrevoked_or_missing_raises_404(self):
        from auth.api.routes.api.jwks import delete_key

        jwks_service = AsyncMock()
        jwks_service.delete = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc:
            await delete_key("kid-1", AsyncMock(), _admin(), jwks_service)

        assert exc.value.status_code == 404
        assert "not revoked" in exc.value.detail
