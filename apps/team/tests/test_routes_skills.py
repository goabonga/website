# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for agent skill management routes."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_team_mock():
    team = MagicMock()
    team.id = uuid4()
    return team


def _make_agent_mock(**kwargs):
    agent = MagicMock()
    agent.id = kwargs.get("id", uuid4())
    agent.team_id = kwargs.get("team_id", uuid4())
    agent.name = kwargs.get("name", "DevAgent")
    return agent


def _make_skill_mock(**kwargs):
    skill = MagicMock()
    skill.id = kwargs.get("id", uuid4())
    skill.agent_id = kwargs.get("agent_id", uuid4())
    skill.team_id = kwargs.get("team_id", uuid4())
    skill.name = kwargs.get("name", "code-review")
    skill.description = kwargs.get("description", "Review code changes.")
    skill.content = kwargs.get("content", "# Code Review\n\nStep 1...")
    skill.license = kwargs.get("license", "")
    skill.compatibility = kwargs.get("compatibility", "")
    skill.metadata_ = kwargs.get("metadata_", {})
    skill.allowed_tools = kwargs.get("allowed_tools", [])
    skill.is_active = kwargs.get("is_active", True)
    skill.created_at = "2026-01-01T00:00:00"
    skill.updated_at = "2026-01-01T00:00:00"
    return skill


class TestCreateSkill:
    @pytest.mark.asyncio
    async def test_create_skill_returns_201(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(
            side_effect=[team_result, agent_result, existing_result]
        )

        response = await auth_client.post(
            f"/platform/{team_id}/agents/{agent_id}/skills",
            json={
                "name": "code-review",
                "description": "Review code for quality.",
                "content": "# Code Review\n\n1. Check style",
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_skill_conflict_409(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = _make_skill_mock()

        mock_db_session.execute = AsyncMock(
            side_effect=[team_result, agent_result, existing_result]
        )

        response = await auth_client.post(
            f"/platform/{team_id}/agents/{agent_id}/skills",
            json={
                "name": "code-review",
                "description": "Review code.",
                "content": "# Review",
            },
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_skill_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills",
            json={"name": "test", "description": "Test.", "content": "# Test"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_skill_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result])

        response = await auth_client.post(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills",
            json={"name": "test", "description": "Test.", "content": "# Test"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_skill_requires_auth(self, client: AsyncClient):
        response = await client.post(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills",
            json={"name": "test", "description": "Test.", "content": "# Test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_skill_invalid_name(self, auth_client: AsyncClient, mock_db_session):
        response = await auth_client.post(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills",
            json={"name": "UPPERCASE", "description": "Test.", "content": "# Test"},
        )
        assert response.status_code == 422


class TestListSkills:
    @pytest.mark.asyncio
    async def test_list_skills_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, list_result])

        response = await auth_client.get(f"/platform/{team_id}/agents/{agent_id}/skills")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_skills_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.get(f"/platform/{uuid4()}/agents/{uuid4()}/skills")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_skills_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result])

        response = await auth_client.get(f"/platform/{uuid4()}/agents/{uuid4()}/skills")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_skills_requires_auth(self, client: AsyncClient):
        response = await client.get(f"/platform/{uuid4()}/agents/{uuid4()}/skills")
        assert response.status_code == 401


class TestGetSkill:
    @pytest.mark.asyncio
    async def test_get_skill_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()
        skill = _make_skill_mock(agent_id=agent_id, team_id=team_id)

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        skill_result = MagicMock()
        skill_result.scalar_one_or_none.return_value = skill

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, skill_result])

        response = await auth_client.get(f"/platform/{team_id}/agents/{agent_id}/skills/{skill.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_skill_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        skill_result = MagicMock()
        skill_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, skill_result])

        response = await auth_client.get(f"/platform/{team_id}/agents/{agent_id}/skills/{uuid4()}")
        assert response.status_code == 404


class TestUpdateSkill:
    @pytest.mark.asyncio
    async def test_update_skill_returns_200(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()
        skill = _make_skill_mock(agent_id=agent_id, team_id=team_id)

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        skill_result = MagicMock()
        skill_result.scalar_one_or_none.return_value = skill

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, skill_result])

        response = await auth_client.patch(
            f"/platform/{team_id}/agents/{agent_id}/skills/{skill.id}",
            json={"description": "Updated description"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_skill_metadata(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()
        skill = _make_skill_mock(agent_id=agent_id, team_id=team_id)

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        skill_result = MagicMock()
        skill_result.scalar_one_or_none.return_value = skill

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, skill_result])

        response = await auth_client.patch(
            f"/platform/{team_id}/agents/{agent_id}/skills/{skill.id}",
            json={"metadata": {"version": "2.0"}},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_skill_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        skill_result = MagicMock()
        skill_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, skill_result])

        response = await auth_client.patch(
            f"/platform/{team_id}/agents/{agent_id}/skills/{uuid4()}",
            json={"description": "Updated"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_skill_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.patch(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills/{uuid4()}",
            json={"description": "Updated"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_skill_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result])

        response = await auth_client.patch(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills/{uuid4()}",
            json={"description": "Updated"},
        )
        assert response.status_code == 404


class TestDeleteSkill:
    @pytest.mark.asyncio
    async def test_delete_skill_returns_204(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()
        skill = _make_skill_mock(agent_id=agent_id, team_id=team_id)

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        skill_result = MagicMock()
        skill_result.scalar_one_or_none.return_value = skill

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, skill_result])

        response = await auth_client.delete(
            f"/platform/{team_id}/agents/{agent_id}/skills/{skill.id}"
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_skill_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_id = uuid4()
        agent_id = uuid4()

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = _make_agent_mock(
            id=agent_id, team_id=team_id
        )

        skill_result = MagicMock()
        skill_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result, skill_result])

        response = await auth_client.delete(
            f"/platform/{team_id}/agents/{agent_id}/skills/{uuid4()}"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_skill_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.delete(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills/{uuid4()}"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_skill_agent_not_found(self, auth_client: AsyncClient, mock_db_session):
        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = _make_team_mock()

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[team_result, agent_result])

        response = await auth_client.delete(
            f"/platform/{uuid4()}/agents/{uuid4()}/skills/{uuid4()}"
        )
        assert response.status_code == 404
