# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for health, discovery, and JWKS routes."""

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
