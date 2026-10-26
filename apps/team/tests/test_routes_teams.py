# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team management routes."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestCreateTeam:
    @pytest.mark.asyncio
    async def test_create_team_returns_201(self, auth_client: AsyncClient, mock_db_session):
        response = await auth_client.post(
            "/platform/team",
            json={"name": "Engineering", "slug": "engineering"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Engineering"
        assert data["slug"] == "engineering"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_team_with_description(self, auth_client: AsyncClient, mock_db_session):
        response = await auth_client.post(
            "/platform/team",
            json={
                "name": "Engineering",
                "slug": "engineering",
                "description": "Eng team",
                "config": {"key": "value"},
            },
        )
        assert response.status_code == 201
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_team_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/platform/team",
            json={"name": "Engineering", "slug": "engineering"},
        )
        assert response.status_code == 401


class TestListTeams:
    @pytest.mark.asyncio
    async def test_list_teams_returns_200(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get("/platform/team")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_teams_requires_auth(self, client: AsyncClient):
        response = await client.get("/platform/team")
        assert response.status_code == 401


class TestGetTeam:
    @pytest.mark.asyncio
    async def test_get_team_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_team = MagicMock()
        mock_team.id = team_id
        mock_team.name = "Engineering"
        mock_team.slug = "engineering"
        mock_team.description = ""
        mock_team.config = {}
        mock_team.is_active = True
        mock_team.created_at = "2024-01-01T00:00:00"
        mock_team.updated_at = "2024-01-01T00:00:00"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/team/{team_id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/team/{uuid4()}")
        assert response.status_code == 404


class TestUpdateTeam:
    @pytest.mark.asyncio
    async def test_update_team_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_team = MagicMock()
        mock_team.id = team_id
        mock_team.name = "Engineering"
        mock_team.slug = "engineering"
        mock_team.description = "Updated"
        mock_team.config = {}
        mock_team.is_active = True
        mock_team.created_at = "2024-01-01T00:00:00"
        mock_team.updated_at = "2024-01-01T00:00:00"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/team/{team_id}",
            json={"description": "Updated"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/team/{uuid4()}",
            json={"description": "Updated"},
        )
        assert response.status_code == 404


class TestDeleteTeam:
    @pytest.mark.asyncio
    async def test_delete_team_returns_204(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_team = MagicMock()
        mock_team.id = team_id
        mock_team.name = "Engineering"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/team/{team_id}")
        assert response.status_code == 204
        mock_db_session.delete.assert_called_once_with(mock_team)

    @pytest.mark.asyncio
    async def test_delete_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/team/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_team_requires_auth(self, client: AsyncClient):
        response = await client.delete(f"/platform/team/{uuid4()}")
        assert response.status_code == 401
