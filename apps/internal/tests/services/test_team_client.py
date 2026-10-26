# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Team API client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from internal.services.team_client import (
    AgentInfo,
    ConversationInfo,
    MemoryEntryInfo,
    MessageInfo,
    SkillInfo,
    TaskInfo,
    TeamClient,
    TeamInfo,
    ToolInfo,
    WorkflowInfo,
)


@pytest.fixture
def client():
    with patch("internal.services.team_client.settings") as s:
        s.team_api_url = "https://team.example.com"
        s.team_socket_path = ""
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield TeamClient()


@pytest.fixture
def socket_client():
    with patch("internal.services.team_client.settings") as s:
        s.team_api_url = "https://team.example.com"
        s.team_socket_path = "/run/team/team.sock"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield TeamClient()


def _token_response(token="test-token"):
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": 3600},
        request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
    )


def _http_error(status_code, method="GET", url="https://team.example.com/x"):
    resp = httpx.Response(status_code, request=httpx.Request(method, url))
    return httpx.HTTPStatusError(str(status_code), request=resp.request, response=resp)


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInit:
    def test_socket_path_sets_localhost(self, socket_client):
        assert socket_client._base_url == "http://localhost"
        assert socket_client._socket_path == "/run/team/team.sock"

    def test_no_socket_uses_api_url(self, client):
        assert client._base_url == "https://team.example.com"
        assert client._socket_path == ""


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


class TestListTeams:
    @pytest.mark.asyncio
    async def test_success(self, client):
        teams_data = [
            {
                "id": "team-1",
                "name": "Engineering",
                "slug": "engineering",
                "description": "Eng team",
                "config": {},
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=teams_data):
            result = await client.list_teams()
            assert len(result) == 1
            assert isinstance(result[0], TeamInfo)
            assert result[0].name == "Engineering"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_teams()
            assert result == []


class TestGetTeam:
    @pytest.mark.asyncio
    async def test_success(self, client):
        team_data = {
            "id": "team-1",
            "name": "Engineering",
            "slug": "engineering",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=team_data):
            result = await client.get_team("team-1")
            assert result is not None
            assert result.name == "Engineering"

    @pytest.mark.asyncio
    async def test_not_found(self, client):
        with patch.object(client, "_request", side_effect=_http_error(404)):
            result = await client.get_team("x")
            assert result is None

    @pytest.mark.asyncio
    async def test_non_404_http_error(self, client):
        with patch.object(client, "_request", side_effect=_http_error(500)):
            result = await client.get_team("x")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_team("x")
            assert result is None


class TestCreateTeam:
    @pytest.mark.asyncio
    async def test_success(self, client):
        team_data = {
            "id": "team-new",
            "name": "New Team",
            "slug": "new-team",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=team_data):
            result = await client.create_team(name="New Team", slug="new-team")
            assert result is not None
            assert result.id == "team-new"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_team(name="Bad", slug="bad")
            assert result is None


class TestUpdateTeam:
    @pytest.mark.asyncio
    async def test_success(self, client):
        team_data = {
            "id": "team-1",
            "name": "Updated",
            "slug": "engineering",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=team_data
        ) as mock_req:
            result = await client.update_team("team-1", name="Updated")
            assert result is not None
            assert result.name == "Updated"
            # Only name should be in the payload
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["json_data"] == {"name": "Updated"}

    @pytest.mark.asyncio
    async def test_all_fields(self, client):
        team_data = {
            "id": "team-1",
            "name": "Full",
            "slug": "engineering",
            "config": {"k": "v"},
            "is_active": False,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=team_data
        ) as mock_req:
            result = await client.update_team(
                "team-1",
                name="Full",
                description="desc",
                config={"k": "v"},
                is_active=False,
            )
            assert result is not None
            payload = mock_req.call_args.kwargs["json_data"]
            assert payload == {
                "name": "Full",
                "description": "desc",
                "config": {"k": "v"},
                "is_active": False,
            }

    @pytest.mark.asyncio
    async def test_no_fields(self, client):
        team_data = {
            "id": "team-1",
            "name": "Same",
            "slug": "engineering",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=team_data
        ) as mock_req:
            result = await client.update_team("team-1")
            assert result is not None
            assert mock_req.call_args.kwargs["json_data"] == {}

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_team("team-1", name="Bad")
            assert result is None


class TestDeleteTeam:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.delete_team("team-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_team("team-1")
            assert result is False


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class TestListAgents:
    @pytest.mark.asyncio
    async def test_success(self, client):
        agents_data = [
            {
                "id": "agent-1",
                "name": "DevAgent",
                "role": "developer",
                "model": "gpt-4o",
                "provider": "openai",
                "config": {},
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=agents_data):
            result = await client.list_agents("team-1")
            assert len(result) == 1
            assert isinstance(result[0], AgentInfo)
            assert result[0].role == "developer"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_agents("team-1")
            assert result == []


class TestGetAgent:
    @pytest.mark.asyncio
    async def test_success(self, client):
        agent_data = {
            "id": "agent-1",
            "name": "DevAgent",
            "role": "developer",
            "model": "gpt-4o",
            "provider": "openai",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=agent_data):
            result = await client.get_agent("team-1", "agent-1")
            assert result is not None
            assert result.name == "DevAgent"

    @pytest.mark.asyncio
    async def test_not_found(self, client):
        with patch.object(client, "_request", side_effect=_http_error(404)):
            result = await client.get_agent("team-1", "x")
            assert result is None

    @pytest.mark.asyncio
    async def test_non_404_http_error(self, client):
        with patch.object(client, "_request", side_effect=_http_error(500)):
            result = await client.get_agent("team-1", "x")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_agent("team-1", "x")
            assert result is None


class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_success(self, client):
        agent_data = {
            "id": "agent-new",
            "name": "NewAgent",
            "role": "sre",
            "model": "gpt-4o",
            "provider": "openai",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=agent_data):
            result = await client.create_agent("team-1", name="NewAgent", role="sre")
            assert result is not None
            assert result.id == "agent-new"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_agent("team-1", name="Bad", role="bad")
            assert result is None


class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_success(self, client):
        agent_data = {
            "id": "agent-1",
            "name": "Updated",
            "role": "developer",
            "model": "gpt-4o",
            "provider": "openai",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=agent_data
        ) as mock_req:
            result = await client.update_agent("team-1", "agent-1", name="Updated")
            assert result is not None
            assert result.name == "Updated"
            assert mock_req.call_args.kwargs["json_data"] == {"name": "Updated"}

    @pytest.mark.asyncio
    async def test_all_fields(self, client):
        agent_data = {
            "id": "agent-1",
            "name": "Full",
            "role": "sre",
            "model": "claude-3",
            "provider": "anthropic",
            "config": {"temp": 0.5},
            "is_active": False,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=agent_data
        ) as mock_req:
            result = await client.update_agent(
                "team-1",
                "agent-1",
                name="Full",
                role="sre",
                description="desc",
                system_prompt="Be helpful",
                model="claude-3",
                provider="anthropic",
                config={"temp": 0.5},
                is_active=False,
            )
            assert result is not None
            payload = mock_req.call_args.kwargs["json_data"]
            assert payload == {
                "name": "Full",
                "role": "sre",
                "description": "desc",
                "system_prompt": "Be helpful",
                "model": "claude-3",
                "provider": "anthropic",
                "config": {"temp": 0.5},
                "is_active": False,
            }

    @pytest.mark.asyncio
    async def test_no_fields(self, client):
        agent_data = {
            "id": "agent-1",
            "name": "Same",
            "role": "developer",
            "model": "gpt-4o",
            "provider": "openai",
            "config": {},
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=agent_data
        ) as mock_req:
            result = await client.update_agent("team-1", "agent-1")
            assert result is not None
            assert mock_req.call_args.kwargs["json_data"] == {}

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_agent("team-1", "agent-1", name="Bad")
            assert result is None


class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.delete_agent("team-1", "agent-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_agent("team-1", "agent-1")
            assert result is False


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestListSkills:
    @pytest.mark.asyncio
    async def test_success(self, client):
        skills_data = [
            {
                "id": "skill-1",
                "agent_id": "agent-1",
                "name": "code-review",
                "description": "Review code changes",
                "content": "Instructions here",
                "allowed_tools": ["create_task"],
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=skills_data):
            result = await client.list_skills("team-1", "agent-1")
            assert len(result) == 1
            assert isinstance(result[0], SkillInfo)
            assert result[0].name == "code-review"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_skills("team-1", "agent-1")
            assert result == []


class TestGetSkill:
    @pytest.mark.asyncio
    async def test_success(self, client):
        skill_data = {
            "id": "skill-1",
            "agent_id": "agent-1",
            "name": "code-review",
            "description": "Review code",
            "content": "Full instructions here",
            "allowed_tools": ["create_task"],
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=skill_data):
            result = await client.get_skill("team-1", "agent-1", "skill-1")
            assert result is not None
            assert isinstance(result, SkillInfo)
            assert result.id == "skill-1"
            assert result.content == "Full instructions here"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_skill("team-1", "agent-1", "skill-1")
            assert result is None


class TestCreateSkill:
    @pytest.mark.asyncio
    async def test_success(self, client):
        skill_data = {
            "id": "skill-new",
            "agent_id": "agent-1",
            "name": "data-analysis",
            "description": "Analyze data",
            "content": "Full instructions",
            "allowed_tools": ["query_db"],
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=skill_data):
            result = await client.create_skill(
                "team-1",
                "agent-1",
                name="data-analysis",
                description="Analyze data",
                content="Full instructions",
                allowed_tools=["query_db"],
            )
            assert result is not None
            assert isinstance(result, SkillInfo)
            assert result.id == "skill-new"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_skill(
                "team-1",
                "agent-1",
                name="bad",
                description="bad",
            )
            assert result is None


class TestUpdateSkill:
    @pytest.mark.asyncio
    async def test_success(self, client):
        skill_data = {
            "id": "skill-1",
            "agent_id": "agent-1",
            "name": "code-review",
            "description": "Updated desc",
            "content": "New instructions",
            "allowed_tools": ["create_task", "send_message"],
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=skill_data):
            result = await client.update_skill(
                "team-1",
                "agent-1",
                "skill-1",
                name="code-review",
                description="Updated desc",
                content="New instructions",
                allowed_tools=["create_task", "send_message"],
                is_active=True,
            )
            assert result is not None
            assert isinstance(result, SkillInfo)
            assert result.description == "Updated desc"

    @pytest.mark.asyncio
    async def test_partial_update(self, client):
        skill_data = {
            "id": "skill-1",
            "agent_id": "agent-1",
            "name": "code-review",
            "description": "Only desc updated",
            "content": "",
            "allowed_tools": [],
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=skill_data
        ) as mock_req:
            result = await client.update_skill(
                "team-1",
                "agent-1",
                "skill-1",
                description="Only desc updated",
            )
            assert result is not None
            assert result.description == "Only desc updated"
            call_data = mock_req.call_args[1]["json_data"]
            assert "name" not in call_data
            assert "content" not in call_data
            assert "allowed_tools" not in call_data
            assert "is_active" not in call_data

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_skill(
                "team-1",
                "agent-1",
                "skill-1",
                name="bad",
            )
            assert result is None


class TestDeleteSkill:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.delete_skill("team-1", "agent-1", "skill-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_skill("team-1", "agent-1", "skill-1")
            assert result is False


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class TestListTools:
    @pytest.mark.asyncio
    async def test_success(self, client):
        tools_data = [
            {
                "name": "github_create_issue",
                "description": "Create a GitHub issue",
                "parameters": {},
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=tools_data):
            result = await client.list_tools()
            assert len(result) == 1
            assert isinstance(result[0], ToolInfo)
            assert result[0].name == "github_create_issue"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_tools()
            assert result == []


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------


class TestListWorkflows:
    @pytest.mark.asyncio
    async def test_success(self, client):
        workflows_data = [
            {
                "id": "wf-1",
                "team_id": "team-1",
                "name": "Deploy",
                "status": "active",
                "steps": {},
                "config": {},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=workflows_data):
            result = await client.list_workflows("team-1")
            assert len(result) == 1
            assert isinstance(result[0], WorkflowInfo)
            assert result[0].name == "Deploy"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_workflows("team-1")
            assert result == []


class TestCreateWorkflow:
    @pytest.mark.asyncio
    async def test_success(self, client):
        wf_data = {
            "id": "wf-new",
            "team_id": "team-1",
            "name": "New WF",
            "status": "draft",
            "steps": {"step1": "do"},
            "config": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=wf_data):
            result = await client.create_workflow("team-1", name="New WF", steps={"step1": "do"})
            assert result is not None
            assert isinstance(result, WorkflowInfo)
            assert result.id == "wf-new"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_workflow("team-1", name="Bad")
            assert result is None


class TestUpdateWorkflow:
    @pytest.mark.asyncio
    async def test_success(self, client):
        wf_data = {
            "id": "wf-1",
            "team_id": "team-1",
            "name": "Updated",
            "status": "active",
            "steps": {},
            "config": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=wf_data
        ) as mock_req:
            result = await client.update_workflow(
                "team-1",
                "wf-1",
                name="Updated",
                description="desc",
                steps={"s": 1},
                status="active",
                config={"c": 2},
            )
            assert result is not None
            assert isinstance(result, WorkflowInfo)
            payload = mock_req.call_args.kwargs["json_data"]
            assert payload == {
                "name": "Updated",
                "description": "desc",
                "steps": {"s": 1},
                "status": "active",
                "config": {"c": 2},
            }

    @pytest.mark.asyncio
    async def test_no_fields(self, client):
        wf_data = {
            "id": "wf-1",
            "team_id": "team-1",
            "name": "Same",
            "status": "draft",
            "steps": {},
            "config": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=wf_data
        ) as mock_req:
            result = await client.update_workflow("team-1", "wf-1")
            assert result is not None
            assert mock_req.call_args.kwargs["json_data"] == {}

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_workflow("team-1", "wf-1", name="Bad")
            assert result is None


class TestDeleteWorkflow:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.delete_workflow("team-1", "wf-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_workflow("team-1", "wf-1")
            assert result is False


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    @pytest.mark.asyncio
    async def test_success(self, client):
        conv_data = [
            {
                "id": "conv-1",
                "slug": "general",
                "title": "General",
                "type": "general",
                "status": "active",
                "extra": {},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=conv_data):
            result = await client.list_conversations()
            assert len(result) == 1
            assert isinstance(result[0], ConversationInfo)
            assert result[0].slug == "general"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_conversations()
            assert result == []


class TestGetConversation:
    @pytest.mark.asyncio
    async def test_success(self, client):
        conv_data = {
            "id": "conv-1",
            "slug": "general",
            "title": "General",
            "type": "general",
            "status": "active",
            "extra": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=conv_data):
            result = await client.get_conversation("conv-1")
            assert result is not None
            assert isinstance(result, ConversationInfo)
            assert result.title == "General"

    @pytest.mark.asyncio
    async def test_not_found(self, client):
        with patch.object(client, "_request", side_effect=_http_error(404)):
            result = await client.get_conversation("x")
            assert result is None

    @pytest.mark.asyncio
    async def test_non_404_http_error(self, client):
        with patch.object(client, "_request", side_effect=_http_error(500)):
            result = await client.get_conversation("x")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_conversation("x")
            assert result is None


class TestCreateConversation:
    @pytest.mark.asyncio
    async def test_success(self, client):
        conv_data = {
            "id": "conv-new",
            "slug": "new-conv",
            "title": "New Conv",
            "type": "general",
            "status": "active",
            "extra": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=conv_data):
            result = await client.create_conversation(slug="new-conv", title="New Conv")
            assert result is not None
            assert isinstance(result, ConversationInfo)
            assert result.id == "conv-new"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_conversation(slug="bad", title="Bad")
            assert result is None


class TestDeleteConversation:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.delete_conversation("conv-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_conversation("conv-1")
            assert result is False


class TestAddAgentToConversation:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.add_agent_to_conversation("conv-1", "agent-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.add_agent_to_conversation("conv-1", "agent-1")
            assert result is False


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class TestListMessages:
    @pytest.mark.asyncio
    async def test_success(self, client):
        msg_data = [
            {
                "id": "msg-1",
                "conversation_id": "conv-1",
                "agent_id": "agent-1",
                "type": "message",
                "content": {},
                "text": "Hello",
                "visibility": "public",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=msg_data):
            result = await client.list_messages("conv-1")
            assert len(result) == 1
            assert isinstance(result[0], MessageInfo)
            assert result[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_messages("conv-1")
            assert result == []


class TestCreateMessage:
    @pytest.mark.asyncio
    async def test_success(self, client):
        msg_data = {
            "id": "msg-new",
            "conversation_id": "conv-1",
            "agent_id": "agent-1",
            "type": "message",
            "content": {},
            "text": "Hi there",
            "visibility": "public",
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=msg_data):
            result = await client.create_message("conv-1", agent_id="agent-1", text="Hi there")
            assert result is not None
            assert isinstance(result, MessageInfo)
            assert result.id == "msg-new"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_message("conv-1", agent_id="agent-1", text="Bad")
            assert result is None


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class TestListMemory:
    @pytest.mark.asyncio
    async def test_success(self, client):
        mem_data = [
            {
                "id": "mem-1",
                "team_id": "team-1",
                "content": "Important fact",
                "extra": {},
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=mem_data):
            result = await client.list_memory("team-1")
            assert len(result) == 1
            assert isinstance(result[0], MemoryEntryInfo)
            assert result[0].content == "Important fact"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_memory("team-1")
            assert result == []


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_success(self, client):
        task_data = {
            "id": "task-new",
            "team_id": "team-1",
            "agent_id": "agent-1",
            "title": "Review PR",
            "description": "Check the code",
            "status": "assigned",
            "priority": 50,
            "input_data": {"prompt": "Check the code"},
            "output_data": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=task_data):
            result = await client.create_task(
                "team-1",
                title="Review PR",
                description="Check the code",
                agent_id="agent-1",
                input_data={"prompt": "Check the code"},
                priority=50,
            )
            assert result is not None
            assert isinstance(result, TaskInfo)
            assert result.id == "task-new"
            assert result.status == "assigned"

    @pytest.mark.asyncio
    async def test_success_without_agent(self, client):
        task_data = {
            "id": "task-new",
            "team_id": "team-1",
            "title": "Pending task",
            "description": "",
            "status": "pending",
            "priority": 0,
            "input_data": {},
            "output_data": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=task_data
        ) as mock_req:
            result = await client.create_task("team-1", title="Pending task")
            assert result is not None
            assert result.status == "pending"
            payload = mock_req.call_args.kwargs["json_data"]
            assert "agent_id" not in payload

    @pytest.mark.asyncio
    async def test_with_agent_sends_agent_id(self, client):
        task_data = {
            "id": "task-new",
            "team_id": "team-1",
            "agent_id": "agent-1",
            "title": "Task",
            "description": "",
            "status": "assigned",
            "priority": 0,
            "input_data": {},
            "output_data": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=task_data
        ) as mock_req:
            await client.create_task("team-1", title="Task", agent_id="agent-1")
            payload = mock_req.call_args.kwargs["json_data"]
            assert payload["agent_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_task("team-1", title="Bad")
            assert result is None


class TestCancelTask:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=None
        ) as mock_req:
            result = await client.cancel_task("team-1", "task-abc")
            assert result is True
            mock_req.assert_awaited_once_with(
                "POST",
                "/platform/team-1/tasks/task-abc/cancel",
                scope="team:platform:write",
            )

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.cancel_task("team-1", "task-abc")
            assert result is False


class TestCreateMemory:
    @pytest.mark.asyncio
    async def test_success(self, client):
        mem_data = {
            "id": "mem-new",
            "team_id": "team-1",
            "content": "New memory",
            "extra": {},
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=mem_data):
            result = await client.create_memory("team-1", content="New memory")
            assert result is not None
            assert result.id == "mem-new"

    @pytest.mark.asyncio
    async def test_with_agent_and_conversation(self, client):
        mem_data = {
            "id": "mem-new",
            "team_id": "team-1",
            "agent_id": "agent-1",
            "conversation_id": "conv-1",
            "content": "Context memory",
            "extra": {},
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=mem_data
        ) as mock_req:
            result = await client.create_memory(
                "team-1",
                content="Context memory",
                agent_id="agent-1",
                conversation_id="conv-1",
            )
            assert result is not None
            payload = mock_req.call_args.kwargs["json_data"]
            assert payload["agent_id"] == "agent-1"
            assert payload["conversation_id"] == "conv-1"

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_memory("team-1", content="Bad")
            assert result is None


class TestDeleteMemory:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.delete_memory("team-1", "mem-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_memory("team-1", "mem-1")
            assert result is False


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------


class TestTokenCaching:
    @pytest.mark.asyncio
    async def test_returns_cached_token(self, client):
        cached_token = "cached-token"
        client._tokens["team:platform:read"] = (
            cached_token,
            datetime.now(UTC) + timedelta(hours=1),
        )
        token = await client._get_access_token()
        assert token == cached_token

    @pytest.mark.asyncio
    async def test_fetches_new_when_expired(self, client):
        client._tokens["team:platform:read"] = (
            "old",
            datetime.now(UTC) - timedelta(hours=1),
        )

        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.team_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token()
            assert token == "new-token"


class TestGetAccessTokenIssuerCheck:
    @pytest.mark.asyncio
    async def test_raises_when_no_issuer(self):
        with patch("internal.services.team_client.settings") as s:
            s.team_api_url = "https://team.example.com"
            s.team_socket_path = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = ""
            c = TeamClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                await c._get_access_token()


# ---------------------------------------------------------------------------
# _request method
# ---------------------------------------------------------------------------


class TestRequestMethod:
    @pytest.mark.asyncio
    async def test_raises_when_not_configured(self):
        with patch("internal.services.team_client.settings") as s:
            s.team_api_url = ""
            s.team_socket_path = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = TeamClient()
            with pytest.raises(ValueError, match="team_api_url not configured"):
                await c._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_full_request_flow(self, client):
        client._tokens["team:platform:read"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )

        mock_http = AsyncMock()
        mock_http.request.return_value = httpx.Response(
            200,
            json={"data": "value"},
            request=httpx.Request("GET", "https://team.example.com/platform/test"),
        )

        with patch("internal.services.team_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("GET", "/platform/test")
            assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_request_204_returns_none(self, client):
        client._tokens["team:platform:read"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )

        mock_http = AsyncMock()
        mock_http.request.return_value = httpx.Response(
            204,
            request=httpx.Request("DELETE", "https://team.example.com/platform/test"),
        )

        with patch("internal.services.team_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("DELETE", "/platform/test")
            assert result is None

    @pytest.mark.asyncio
    async def test_token_error_propagates(self, client):
        with (
            patch.object(client, "_get_access_token", side_effect=Exception("token fail")),
            pytest.raises(Exception, match="token fail"),
        ):
            await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_socket_transport(self, socket_client):
        socket_client._tokens["team:platform:read"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )

        mock_http = AsyncMock()
        mock_http.request.return_value = httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("GET", "http://localhost/platform/test"),
        )

        with patch("internal.services.team_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await socket_client._request("GET", "/platform/test")
            assert result == {"ok": True}
            # Verify transport kwarg was passed (UDS)
            call_kwargs = MockClient.call_args.kwargs
            assert call_kwargs.get("transport") is not None
