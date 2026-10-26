# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for health, discovery, and JWKS routes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_healthy(self):
        from auth.api.routes.health import health

        result = await health()
        assert result.status == "healthy"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# JWKS
# ---------------------------------------------------------------------------


class TestJWKS:
    @pytest.mark.asyncio
    async def test_returns_keys(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        jwks_service = MagicMock()

        key1 = MagicMock()
        key2 = MagicMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[key1, key2])
        jwks_service.to_jwk_public.side_effect = [
            {"kty": "RSA", "kid": "k1"},
            {"kty": "RSA", "kid": "k2"},
        ]

        result = (await jwks(db, jwks_service)).model_dump()

        assert len(result["keys"]) == 2
        assert result["keys"][0]["kid"] == "k1"
        assert result["keys"][1]["kid"] == "k2"

    @pytest.mark.asyncio
    async def test_returns_empty_keys(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        jwks_service = MagicMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[])

        result = (await jwks(db, jwks_service)).model_dump()

        assert result["keys"] == []
