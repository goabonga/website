# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the tool catalog route."""

import pytest
import team.services.tools  # noqa: F401 — trigger registration
from httpx import AsyncClient


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_returns_200(self, auth_client: AsyncClient):
        response = await auth_client.get("/platform/tools")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_list_tools_contains_expected_fields(self, auth_client: AsyncClient):
        response = await auth_client.get("/platform/tools")
        data = response.json()
        for tool in data:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool

    @pytest.mark.asyncio
    async def test_list_tools_includes_activate_skill(self, auth_client: AsyncClient):
        response = await auth_client.get("/platform/tools")
        data = response.json()
        names = [t["name"] for t in data]
        assert "activate_skill" in names

    @pytest.mark.asyncio
    async def test_list_tools_requires_auth(self, client: AsyncClient):
        response = await client.get("/platform/tools")
        assert response.status_code == 401
