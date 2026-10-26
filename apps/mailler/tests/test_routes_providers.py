# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GET /api/v1/providers route."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


class TestListProviders:
    """Tests for GET /api/v1/providers endpoint."""

    @pytest.mark.asyncio
    async def test_list_providers(self, auth_client: AsyncClient):
        """GET /api/v1/providers should return list of available providers."""
        with patch(
            "mailler.routes.providers.get_available_providers",
            return_value=["brevo", "ses"],
        ):
            response = await auth_client.get("/api/v1/providers")

        assert response.status_code == 200
        data = response.json()
        assert data["providers"] == ["brevo", "ses"]

    @pytest.mark.asyncio
    async def test_list_providers_unauthenticated(self, client: AsyncClient):
        """GET /api/v1/providers without auth should return 401."""
        response = await client.get("/api/v1/providers")

        assert response.status_code == 401
