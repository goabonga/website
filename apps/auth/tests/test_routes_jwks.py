# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.jwks — JWKS endpoint."""

from unittest.mock import AsyncMock, MagicMock

import pytest

MODULE = "auth.api.routes.jwks"


class TestJWKSEndpoint:
    @pytest.mark.asyncio
    async def test_returns_empty_keyset(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        jwks_service = AsyncMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[])

        result = (await jwks(db, jwks_service)).model_dump()

        assert result == {"keys": []}
        jwks_service.get_all_public_keys.assert_awaited_once_with(db)

    @pytest.mark.asyncio
    async def test_returns_single_key(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        key1 = MagicMock()
        jwks_service = AsyncMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[key1])
        jwks_service.to_jwk_public = MagicMock(
            return_value={
                "kty": "RSA",
                "kid": "key-1",
                "use": "sig",
                "n": "abc123",
                "e": "AQAB",
            }
        )

        result = (await jwks(db, jwks_service)).model_dump()

        assert len(result["keys"]) == 1
        assert result["keys"][0]["kty"] == "RSA"
        assert result["keys"][0]["kid"] == "key-1"
        jwks_service.to_jwk_public.assert_called_once_with(key1)

    @pytest.mark.asyncio
    async def test_returns_multiple_keys(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        key1 = MagicMock()
        key2 = MagicMock()
        key3 = MagicMock()
        jwks_service = AsyncMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[key1, key2, key3])
        jwks_service.to_jwk_public = MagicMock(
            side_effect=[
                {"kty": "RSA", "kid": "key-1", "use": "sig", "n": "n1", "e": "AQAB"},
                {"kty": "RSA", "kid": "key-2", "use": "sig", "n": "n2", "e": "AQAB"},
                {"kty": "RSA", "kid": "key-3", "use": "sig", "n": "n3", "e": "AQAB"},
            ]
        )

        result = (await jwks(db, jwks_service)).model_dump()

        assert len(result["keys"]) == 3
        assert result["keys"][0]["kid"] == "key-1"
        assert result["keys"][1]["kid"] == "key-2"
        assert result["keys"][2]["kid"] == "key-3"
        assert jwks_service.to_jwk_public.call_count == 3

    @pytest.mark.asyncio
    async def test_keys_format(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        key = MagicMock()
        jwks_service = AsyncMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[key])
        jwks_service.to_jwk_public = MagicMock(
            return_value={
                "kty": "RSA",
                "kid": "test-key-id",
                "use": "sig",
                "alg": "RS256",
                "n": "modulus_value",
                "e": "AQAB",
            }
        )

        result = (await jwks(db, jwks_service)).model_dump()

        jwk = result["keys"][0]
        assert jwk["kty"] == "RSA"
        assert jwk["use"] == "sig"
        assert jwk["alg"] == "RS256"
        assert "n" in jwk
        assert "e" in jwk
