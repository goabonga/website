# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for workflow management routes."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_team_mock():
    team = MagicMock()
    team.id = uuid4()
    return team


def _make_workflow_mock(team_id):
    wf = MagicMock()
    wf.id = uuid4()
    wf.team_id = team_id
    wf.name = "Deploy Pipeline"
    wf.description = ""
    wf.steps = {}
    wf.config = {}
    wf.status = "draft"
    wf.created_at = "2024-01-01T00:00:00"
    wf.updated_at = "2024-01-01T00:00:00"
    return wf


class TestCreateWorkflow:
    @pytest.mark.asyncio
    async def test_create_workflow_returns_201(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{team_id}/workflows",
            json={"name": "Deploy Pipeline"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Deploy Pipeline"

    @pytest.mark.asyncio
    async def test_create_workflow_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{uuid4()}/workflows",
            json={"name": "Deploy Pipeline"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_workflow_requires_auth(self, client: AsyncClient):
        response = await client.post(
            f"/platform/{uuid4()}/workflows",
            json={"name": "Deploy Pipeline"},
        )
        assert response.status_code == 401


class TestListWorkflows:
    @pytest.mark.asyncio
    async def test_list_workflows_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[team_result, list_result])

        response = await auth_client.get(f"/platform/{team_id}/workflows")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_workflows_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/{uuid4()}/workflows")
        assert response.status_code == 404


class TestUpdateWorkflow:
    @pytest.mark.asyncio
    async def test_update_workflow_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        wf = _make_workflow_mock(team_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = wf
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/{team_id}/workflows/{wf.id}",
            json={"name": "Updated Pipeline"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_workflow_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/{uuid4()}/workflows/{uuid4()}",
            json={"name": "Updated"},
        )
        assert response.status_code == 404


class TestDeleteWorkflow:
    @pytest.mark.asyncio
    async def test_delete_workflow_returns_204(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        wf = _make_workflow_mock(team_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = wf
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/{team_id}/workflows/{wf.id}")
        assert response.status_code == 204
        mock_db_session.delete.assert_called_once_with(wf)

    @pytest.mark.asyncio
    async def test_delete_workflow_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(f"/platform/{uuid4()}/workflows/{uuid4()}")
        assert response.status_code == 404
