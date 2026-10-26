# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.team route handlers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import RedirectResponse
from internal.auth.models import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**kwargs):
    defaults = {
        "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "email": "test@example.com",
        "name": "Test User",
        "scopes": ["*"],
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    form_mock = MagicMock()
    form_mock.getlist.return_value = []
    req.form = AsyncMock(return_value=form_mock)
    return req


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestTeamDashboard:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import team_dashboard

        mock_client.list_teams = AsyncMock(return_value=[{"id": "t1", "name": "Eng"}])
        user = _make_user()
        request = _make_request(query_params={"success": "ok"})

        await team_dashboard(request, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["teams"] == [{"id": "t1", "name": "Eng"}]
        assert ctx["success"] == "ok"

    async def test_redirect_auth(self):
        from internal.routes.team import team_dashboard

        redirect = RedirectResponse(url="/login")
        result = await team_dashboard(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# Teams CRUD
# ---------------------------------------------------------------------------


class TestTeamNew:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_shows_form(self, mock_templates, mock_client):
        from internal.routes.team import team_new

        user = _make_user()
        request = _make_request()

        await team_new(request, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["team"] is None
        assert ctx["is_edit"] is False

    async def test_redirect_auth(self):
        from internal.routes.team import team_new

        redirect = RedirectResponse(url="/login")
        result = await team_new(MagicMock(), auth_result=redirect)
        assert result is redirect


class TestTeamCreate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import team_create

        mock_team = MagicMock(id="team-new", name="New Team")
        mock_client.create_team = AsyncMock(return_value=mock_team)
        user = _make_user()
        request = _make_request()

        result = await team_create(
            request,
            name="New Team",
            slug="new-team",
            description="",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import team_create

        mock_client.create_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await team_create(
            request,
            name="Bad",
            slug="bad",
            description="",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.team import team_create

        user = _make_user()
        request = _make_request()

        result = await team_create(
            request,
            name="T",
            slug="t",
            description="",
            config_json="{invalid",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import team_create

        redirect = RedirectResponse(url="/login")
        result = await team_create(
            MagicMock(),
            name="",
            slug="",
            description="",
            config_json="{}",
            auth_result=redirect,
        )
        assert result is redirect


class TestTeamDetail:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import team_detail

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_agents = AsyncMock(return_value=[])
        mock_client.list_workflows = AsyncMock(return_value=[])
        mock_client.list_memory = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await team_detail(request, team_id="t1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["team"] is mock_team

    @patch("internal.routes.team.team_client")
    async def test_not_found(self, mock_client):
        from internal.routes.team import team_detail

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await team_detail(request, team_id="x", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import team_detail

        redirect = RedirectResponse(url="/login")
        result = await team_detail(MagicMock(), team_id="t1", auth_result=redirect)
        assert result is redirect


class TestTeamEdit:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import team_edit

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        user = _make_user()
        request = _make_request()

        await team_edit(request, team_id="t1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["team"] is mock_team
        assert ctx["is_edit"] is True

    @patch("internal.routes.team.team_client")
    async def test_not_found(self, mock_client):
        from internal.routes.team import team_edit

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await team_edit(request, team_id="x", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import team_edit

        redirect = RedirectResponse(url="/login")
        result = await team_edit(MagicMock(), team_id="t1", auth_result=redirect)
        assert result is redirect


class TestTeamUpdate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import team_update

        mock_team = MagicMock(id="t1")
        mock_client.update_team = AsyncMock(return_value=mock_team)
        user = _make_user()
        request = _make_request()

        result = await team_update(
            request,
            team_id="t1",
            name="Updated",
            description="d",
            config_json="{}",
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import team_update

        mock_client.update_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await team_update(
            request,
            team_id="t1",
            name="Bad",
            description="",
            config_json="{}",
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+update" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.team import team_update

        user = _make_user()
        request = _make_request()

        result = await team_update(
            request,
            team_id="t1",
            name="T",
            description="",
            config_json="{broken",
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid+JSON" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import team_update

        redirect = RedirectResponse(url="/login")
        result = await team_update(
            MagicMock(),
            team_id="t1",
            name="",
            description="",
            config_json="{}",
            is_active=True,
            auth_result=redirect,
        )
        assert result is redirect


class TestTeamDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import team_delete

        mock_client.delete_team = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await team_delete(request, team_id="t1", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import team_delete

        mock_client.delete_team = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await team_delete(request, team_id="t1", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import team_delete

        redirect = RedirectResponse(url="/login")
        result = await team_delete(MagicMock(), team_id="t1", auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# Agents CRUD
# ---------------------------------------------------------------------------


class TestAgentsList:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import agents_list

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_agents = AsyncMock(return_value=[{"id": "a1"}])
        user = _make_user()
        request = _make_request()

        await agents_list(request, team_id="t1", page=1, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["agents"] == [{"id": "a1"}]

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import agents_list

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await agents_list(request, team_id="x", page=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import agents_list

        redirect = RedirectResponse(url="/login")
        result = await agents_list(
            MagicMock(),
            team_id="t1",
            page=1,
            auth_result=redirect,
        )
        assert result is redirect


class TestAgentNew:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_shows_form(self, mock_templates, mock_client):
        from internal.routes.team import agent_new

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_tools = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await agent_new(request, team_id="t1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["agent"] is None
        assert ctx["is_edit"] is False
        assert ctx["available_tools"] == []
        assert ctx["advanced_config"] == {}

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import agent_new

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await agent_new(request, team_id="x", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import agent_new

        redirect = RedirectResponse(url="/login")
        result = await agent_new(MagicMock(), team_id="t1", auth_result=redirect)
        assert result is redirect


class TestAgentCreate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import agent_create

        mock_agent = MagicMock(id="agent-new", name="NewAgent")
        mock_client.create_agent = AsyncMock(return_value=mock_agent)
        user = _make_user()
        request = _make_request()

        result = await agent_create(
            request,
            team_id="t1",
            name="NewAgent",
            role="dev",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import agent_create

        mock_client.create_agent = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await agent_create(
            request,
            team_id="t1",
            name="Bad",
            role="bad",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.team import agent_create

        user = _make_user()
        request = _make_request()

        result = await agent_create(
            request,
            team_id="t1",
            name="A",
            role="r",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{bad",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid+JSON" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_success_with_tools_and_credentials(self, mock_client):
        from internal.routes.team import agent_create

        mock_agent = MagicMock(id="agent-new", name="NewAgent")
        mock_client.create_agent = AsyncMock(return_value=mock_agent)
        user = _make_user()

        form_mock = MagicMock()
        form_mock.getlist.side_effect = lambda key: {
            "tools": ["github_create_issue", "git_clone"],
            "credential_keys": ["github_token", "api_key", "empty_val", ""],
            "credential_values": ["ghp_xxxx", "sk-1234", "", "ignored"],
        }.get(key, [])
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await agent_create(
            request,
            team_id="t1",
            name="NewAgent",
            role="dev",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            max_iterations=15,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]
        call_kwargs = mock_client.create_agent.call_args.kwargs
        assert call_kwargs["config"]["tools"] == ["github_create_issue", "git_clone"]
        assert call_kwargs["config"]["max_iterations"] == 15
        assert call_kwargs["config"]["credentials"] == {
            "github_token": "ghp_xxxx",
            "api_key": "sk-1234",
        }

    async def test_redirect_auth(self):
        from internal.routes.team import agent_create

        redirect = RedirectResponse(url="/login")
        result = await agent_create(
            MagicMock(),
            team_id="t1",
            name="",
            role="",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            auth_result=redirect,
        )
        assert result is redirect


class TestAgentDetail:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import agent_detail

        mock_team = MagicMock(id="t1")
        mock_agent = MagicMock(id="a1")
        mock_skills = [MagicMock(id="s1")]
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.get_agent = AsyncMock(return_value=mock_agent)
        mock_client.list_skills = AsyncMock(return_value=mock_skills)
        user = _make_user()
        request = _make_request()

        await agent_detail(request, team_id="t1", agent_id="a1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["agent"] is mock_agent
        assert ctx["skills"] is mock_skills

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import agent_detail

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await agent_detail(
            request,
            team_id="x",
            agent_id="a1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_agent_not_found(self, mock_client):
        from internal.routes.team import agent_detail

        mock_client.get_team = AsyncMock(return_value=MagicMock())
        mock_client.get_agent = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await agent_detail(
            request,
            team_id="t1",
            agent_id="x",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Agent+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import agent_detail

        redirect = RedirectResponse(url="/login")
        result = await agent_detail(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            auth_result=redirect,
        )
        assert result is redirect


class TestAgentEdit:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import agent_edit

        mock_team = MagicMock(id="t1")
        mock_agent = MagicMock(
            id="a1",
            config={
                "tools": ["git_clone"],
                "max_iterations": 15,
                "credentials": {"key": "val"},
                "extra_field": "x",
            },
        )
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.get_agent = AsyncMock(return_value=mock_agent)
        mock_client.list_skills = AsyncMock(return_value=[])
        mock_client.list_tools = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await agent_edit(request, team_id="t1", agent_id="a1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["agent"] is mock_agent
        assert ctx["is_edit"] is True
        assert ctx["skills"] == []
        assert ctx["available_tools"] == []
        assert ctx["advanced_config"] == {"extra_field": "x"}

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import agent_edit

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await agent_edit(
            request,
            team_id="x",
            agent_id="a1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_agent_not_found(self, mock_client):
        from internal.routes.team import agent_edit

        mock_client.get_team = AsyncMock(return_value=MagicMock())
        mock_client.get_agent = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await agent_edit(
            request,
            team_id="t1",
            agent_id="x",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Agent+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import agent_edit

        redirect = RedirectResponse(url="/login")
        result = await agent_edit(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            auth_result=redirect,
        )
        assert result is redirect


class TestAgentUpdate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import agent_update

        mock_agent = MagicMock(id="a1")
        mock_client.update_agent = AsyncMock(return_value=mock_agent)
        mock_client.get_agent = AsyncMock(return_value=MagicMock(config={}))
        user = _make_user()
        request = _make_request()

        result = await agent_update(
            request,
            team_id="t1",
            agent_id="a1",
            name="Updated",
            role="dev",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            max_iterations=10,
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import agent_update

        mock_client.update_agent = AsyncMock(return_value=None)
        mock_client.get_agent = AsyncMock(return_value=MagicMock(config={}))
        user = _make_user()
        request = _make_request()

        result = await agent_update(
            request,
            team_id="t1",
            agent_id="a1",
            name="Bad",
            role="dev",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            max_iterations=10,
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+update" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.team import agent_update

        user = _make_user()
        request = _make_request()

        result = await agent_update(
            request,
            team_id="t1",
            agent_id="a1",
            name="A",
            role="r",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{bad",
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid+JSON" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_credential_merge_preserves_existing(self, mock_client):
        from internal.routes.team import agent_update

        mock_agent = MagicMock(id="a1")
        existing_agent = MagicMock(
            config={"credentials": {"github_token": "existing-secret"}},
        )
        mock_client.update_agent = AsyncMock(return_value=mock_agent)
        mock_client.get_agent = AsyncMock(return_value=existing_agent)
        user = _make_user()

        form_mock = MagicMock()
        form_mock.getlist.side_effect = lambda key: {
            "tools": [],
            "credential_keys": ["github_token", "api_key", "unknown_key"],
            "credential_values": ["", "new-key", ""],
            "credential_remove": [],
        }.get(key, [])
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await agent_update(
            request,
            team_id="t1",
            agent_id="a1",
            name="Updated",
            role="dev",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            max_iterations=10,
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]
        creds = mock_client.update_agent.call_args.kwargs["config"]["credentials"]
        assert creds["github_token"] == "existing-secret"
        assert creds["api_key"] == "new-key"
        assert "unknown_key" not in creds

    @patch("internal.routes.team.team_client")
    async def test_credential_removal(self, mock_client):
        from internal.routes.team import agent_update

        mock_agent = MagicMock(id="a1")
        existing_agent = MagicMock(
            config={
                "credentials": {
                    "github_token": "existing-secret",
                    "api_key": "old-key",
                },
            },
        )
        mock_client.update_agent = AsyncMock(return_value=mock_agent)
        mock_client.get_agent = AsyncMock(return_value=existing_agent)
        user = _make_user()

        form_mock = MagicMock()
        form_mock.getlist.side_effect = lambda key: {
            "tools": ["git_clone"],
            "credential_keys": ["github_token", "api_key"],
            "credential_values": ["", ""],
            "credential_remove": ["api_key"],
        }.get(key, [])
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await agent_update(
            request,
            team_id="t1",
            agent_id="a1",
            name="Updated",
            role="dev",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            max_iterations=10,
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]
        config = mock_client.update_agent.call_args.kwargs["config"]
        assert config["tools"] == ["git_clone"]
        assert "api_key" not in config["credentials"]
        assert config["credentials"]["github_token"] == "existing-secret"

    async def test_redirect_auth(self):
        from internal.routes.team import agent_update

        redirect = RedirectResponse(url="/login")
        result = await agent_update(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            name="",
            role="",
            description="",
            system_prompt="",
            model="gpt-4o",
            provider="openai",
            config_json="{}",
            is_active=True,
            auth_result=redirect,
        )
        assert result is redirect


class TestAgentDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import agent_delete

        mock_client.delete_agent = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await agent_delete(
            request,
            team_id="t1",
            agent_id="a1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import agent_delete

        mock_client.delete_agent = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await agent_delete(
            request,
            team_id="t1",
            agent_id="a1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import agent_delete

        redirect = RedirectResponse(url="/login")
        result = await agent_delete(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestSkillCreate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import skill_create

        mock_skill = MagicMock(name="code-review")
        mock_client.create_skill = AsyncMock(return_value=mock_skill)
        user = _make_user()
        request = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["create_task", "send_message"]
        request.form = AsyncMock(return_value=form_mock)

        result = await skill_create(
            request,
            team_id="t1",
            agent_id="a1",
            skill_name="code-review",
            skill_description="Review code",
            skill_content="Instructions",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Skill+created" in result.headers["location"]
        mock_client.create_skill.assert_awaited_once_with(
            team_id="t1",
            agent_id="a1",
            name="code-review",
            description="Review code",
            content="Instructions",
            allowed_tools=["create_task", "send_message"],
        )

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import skill_create

        mock_client.create_skill = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await skill_create(
            request,
            team_id="t1",
            agent_id="a1",
            skill_name="bad",
            skill_description="bad",
            skill_content="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+create+skill" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_empty_allowed_tools(self, mock_client):
        from internal.routes.team import skill_create

        mock_skill = MagicMock(name="simple")
        mock_client.create_skill = AsyncMock(return_value=mock_skill)
        user = _make_user()
        request = _make_request()

        await skill_create(
            request,
            team_id="t1",
            agent_id="a1",
            skill_name="simple",
            skill_description="Simple skill",
            skill_content="",
            auth_result=user,
        )

        call_kwargs = mock_client.create_skill.call_args.kwargs
        assert call_kwargs["allowed_tools"] == []

    async def test_redirect_auth(self):
        from internal.routes.team import skill_create

        redirect = RedirectResponse(url="/login")
        result = await skill_create(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            skill_name="",
            skill_description="",
            skill_content="",
            auth_result=redirect,
        )
        assert result is redirect


class TestSkillDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import skill_delete

        mock_client.delete_skill = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await skill_delete(
            request,
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Skill+deleted" in result.headers["location"]
        mock_client.delete_skill.assert_awaited_once_with("t1", "a1", "s1")

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import skill_delete

        mock_client.delete_skill = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await skill_delete(
            request,
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+delete+skill" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import skill_delete

        redirect = RedirectResponse(url="/login")
        result = await skill_delete(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            auth_result=redirect,
        )
        assert result is redirect


class TestSkillEdit:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import skill_edit

        mock_team = MagicMock(id="t1")
        mock_agent = MagicMock(id="a1")
        mock_skill = MagicMock(id="s1", name="code-review")
        mock_tools = [MagicMock(name="create_task")]
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.get_agent = AsyncMock(return_value=mock_agent)
        mock_client.get_skill = AsyncMock(return_value=mock_skill)
        mock_client.list_tools = AsyncMock(return_value=mock_tools)
        user = _make_user()
        request = _make_request()

        await skill_edit(request, team_id="t1", agent_id="a1", skill_id="s1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["skill"] is mock_skill
        assert ctx["agent"] is mock_agent
        assert ctx["available_tools"] is mock_tools
        mock_client.get_skill.assert_awaited_once_with("t1", "a1", "s1")

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import skill_edit

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await skill_edit(
            request,
            team_id="x",
            agent_id="a1",
            skill_id="s1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_agent_not_found(self, mock_client):
        from internal.routes.team import skill_edit

        mock_client.get_team = AsyncMock(return_value=MagicMock())
        mock_client.get_agent = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await skill_edit(
            request,
            team_id="t1",
            agent_id="x",
            skill_id="s1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Agent+not+found" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_skill_not_found(self, mock_client):
        from internal.routes.team import skill_edit

        mock_client.get_team = AsyncMock(return_value=MagicMock())
        mock_client.get_agent = AsyncMock(return_value=MagicMock())
        mock_client.get_skill = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await skill_edit(
            request,
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Skill+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import skill_edit

        redirect = RedirectResponse(url="/login")
        result = await skill_edit(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            auth_result=redirect,
        )
        assert result is redirect


class TestSkillUpdate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import skill_update

        mock_skill = MagicMock(name="code-review")
        mock_client.update_skill = AsyncMock(return_value=mock_skill)
        user = _make_user()
        request = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["create_task", "send_message"]
        request.form = AsyncMock(return_value=form_mock)

        result = await skill_update(
            request,
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            skill_name="code-review",
            skill_description="Updated desc",
            skill_content="New instructions",
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Skill+updated" in result.headers["location"]
        mock_client.update_skill.assert_awaited_once_with(
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            name="code-review",
            description="Updated desc",
            content="New instructions",
            allowed_tools=["create_task", "send_message"],
            is_active=True,
        )

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import skill_update

        mock_client.update_skill = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await skill_update(
            request,
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            skill_name="bad",
            skill_description="bad",
            skill_content="",
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+update+skill" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_empty_allowed_tools(self, mock_client):
        from internal.routes.team import skill_update

        mock_skill = MagicMock(name="simple")
        mock_client.update_skill = AsyncMock(return_value=mock_skill)
        user = _make_user()
        request = _make_request()

        await skill_update(
            request,
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            skill_name="simple",
            skill_description="Simple skill",
            skill_content="",
            is_active=True,
            auth_result=user,
        )

        call_kwargs = mock_client.update_skill.call_args.kwargs
        assert call_kwargs["allowed_tools"] == []

    async def test_redirect_auth(self):
        from internal.routes.team import skill_update

        redirect = RedirectResponse(url="/login")
        result = await skill_update(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            skill_id="s1",
            skill_name="",
            skill_description="",
            skill_content="",
            is_active=True,
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Workflows CRUD
# ---------------------------------------------------------------------------


class TestWorkflowsList:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import workflows_list

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_workflows = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await workflows_list(request, team_id="t1", page=1, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import workflows_list

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await workflows_list(
            request,
            team_id="x",
            page=1,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import workflows_list

        redirect = RedirectResponse(url="/login")
        result = await workflows_list(
            MagicMock(),
            team_id="t1",
            page=1,
            auth_result=redirect,
        )
        assert result is redirect


class TestWorkflowNew:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_shows_form(self, mock_templates, mock_client):
        from internal.routes.team import workflow_new

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_agents = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await workflow_new(request, team_id="t1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["workflow"] is None
        assert ctx["is_edit"] is False
        assert ctx["agents"] == []

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import workflow_new

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await workflow_new(request, team_id="x", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import workflow_new

        redirect = RedirectResponse(url="/login")
        result = await workflow_new(MagicMock(), team_id="t1", auth_result=redirect)
        assert result is redirect


class TestWorkflowCreate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import workflow_create

        mock_wf = MagicMock(id="wf-new")
        mock_client.create_workflow = AsyncMock(return_value=mock_wf)
        user = _make_user()
        request = _make_request()

        result = await workflow_create(
            request,
            team_id="t1",
            name="Deploy",
            description="",
            steps_json="{}",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import workflow_create

        mock_client.create_workflow = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await workflow_create(
            request,
            team_id="t1",
            name="Bad",
            description="",
            steps_json="{}",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+create" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.team import workflow_create

        user = _make_user()
        request = _make_request()

        result = await workflow_create(
            request,
            team_id="t1",
            name="Bad",
            description="",
            steps_json="{invalid",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import workflow_create

        redirect = RedirectResponse(url="/login")
        result = await workflow_create(
            MagicMock(),
            team_id="t1",
            name="",
            description="",
            steps_json="{}",
            config_json="{}",
            auth_result=redirect,
        )
        assert result is redirect


class TestWorkflowEdit:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import workflow_edit

        mock_team = MagicMock(id="t1")
        mock_wf = MagicMock(id="wf-1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_workflows = AsyncMock(return_value=[mock_wf])
        mock_client.list_agents = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await workflow_edit(
            request,
            team_id="t1",
            workflow_id="wf-1",
            auth_result=user,
        )

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["workflow"] is mock_wf
        assert ctx["is_edit"] is True
        assert ctx["agents"] == []

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import workflow_edit

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await workflow_edit(
            request,
            team_id="x",
            workflow_id="wf-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_workflow_not_found(self, mock_client):
        from internal.routes.team import workflow_edit

        mock_client.get_team = AsyncMock(return_value=MagicMock())
        mock_client.list_workflows = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        result = await workflow_edit(
            request,
            team_id="t1",
            workflow_id="nonexistent",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Workflow+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import workflow_edit

        redirect = RedirectResponse(url="/login")
        result = await workflow_edit(
            MagicMock(),
            team_id="t1",
            workflow_id="wf-1",
            auth_result=redirect,
        )
        assert result is redirect


class TestWorkflowUpdate:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import workflow_update

        mock_wf = MagicMock(id="wf-1")
        mock_client.update_workflow = AsyncMock(return_value=mock_wf)
        user = _make_user()
        request = _make_request()

        result = await workflow_update(
            request,
            team_id="t1",
            workflow_id="wf-1",
            name="Updated",
            description="d",
            steps_json="{}",
            workflow_status="active",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import workflow_update

        mock_client.update_workflow = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await workflow_update(
            request,
            team_id="t1",
            workflow_id="wf-1",
            name="Bad",
            description="",
            steps_json="{}",
            workflow_status="draft",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+update" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.team import workflow_update

        user = _make_user()
        request = _make_request()

        result = await workflow_update(
            request,
            team_id="t1",
            workflow_id="wf-1",
            name="U",
            description="",
            steps_json="{bad",
            workflow_status="draft",
            config_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid+JSON" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import workflow_update

        redirect = RedirectResponse(url="/login")
        result = await workflow_update(
            MagicMock(),
            team_id="t1",
            workflow_id="wf-1",
            name="",
            description="",
            steps_json="{}",
            workflow_status="draft",
            config_json="{}",
            auth_result=redirect,
        )
        assert result is redirect


class TestWorkflowDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import workflow_delete

        mock_client.delete_workflow = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await workflow_delete(
            request,
            team_id="t1",
            workflow_id="wf-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import workflow_delete

        mock_client.delete_workflow = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await workflow_delete(
            request,
            team_id="t1",
            workflow_id="wf-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+delete" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import workflow_delete

        redirect = RedirectResponse(url="/login")
        result = await workflow_delete(
            MagicMock(),
            team_id="t1",
            workflow_id="wf-1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Run Agent
# ---------------------------------------------------------------------------


class TestRunAgentForm:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import run_agent_form

        team_mock = MagicMock(id="t1")
        team_mock.name = "Eng"
        agent_mock = MagicMock(id="a1", role="ceo")
        agent_mock.name = "CEO"
        mock_client.get_team = AsyncMock(return_value=team_mock)
        mock_client.list_agents = AsyncMock(return_value=[agent_mock])
        user = _make_user()
        request = _make_request(query_params={"error": "some error"})

        await run_agent_form(request, team_id="t1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["team"].name == "Eng"
        assert len(ctx["agents"]) == 1
        assert ctx["error"] == "some error"

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import run_agent_form

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await run_agent_form(request, team_id="x", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import run_agent_form

        redirect = RedirectResponse(url="/login")
        result = await run_agent_form(MagicMock(), team_id="t1", auth_result=redirect)
        assert result is redirect


class TestRunAgentSubmit:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import run_agent_submit

        mock_task = MagicMock(id="task-new")
        mock_client.create_task = AsyncMock(return_value=mock_task)
        user = _make_user()
        request = _make_request()

        result = await run_agent_submit(
            request,
            team_id="t1",
            agent_id="a1",
            title="Analyze logs",
            message="Check the deployment logs",
            priority=50,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Agent+task+launched" in result.headers["location"]
        mock_client.create_task.assert_called_once_with(
            team_id="t1",
            title="Analyze logs",
            description="Check the deployment logs",
            agent_id="a1",
            input_data={"prompt": "Check the deployment logs"},
            priority=50,
        )

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import run_agent_submit

        mock_client.create_task = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await run_agent_submit(
            request,
            team_id="t1",
            agent_id="a1",
            title="Bad task",
            message="Will fail",
            priority=0,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+launch" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import run_agent_submit

        redirect = RedirectResponse(url="/login")
        result = await run_agent_submit(
            MagicMock(),
            team_id="t1",
            agent_id="a1",
            title="X",
            message="Y",
            priority=0,
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class TestConversationsList:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import conversations_list

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_conversations = AsyncMock(return_value=[])
        mock_client.list_agents = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await conversations_list(request, team_id="t1", page=1, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import conversations_list

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await conversations_list(
            request,
            team_id="x",
            page=1,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import conversations_list

        redirect = RedirectResponse(url="/login")
        result = await conversations_list(
            MagicMock(),
            team_id="t1",
            page=1,
            auth_result=redirect,
        )
        assert result is redirect


class TestConversationDetail:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import conversation_detail

        mock_team = MagicMock(id="t1")
        mock_conv = MagicMock(id="conv-1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.get_conversation = AsyncMock(return_value=mock_conv)
        mock_client.list_messages = AsyncMock(return_value=[])
        mock_client.list_agents = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await conversation_detail(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["conversation"] is mock_conv

    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_tool_call_map(self, mock_templates, mock_client):
        from internal.routes.team import conversation_detail

        mock_team = MagicMock(id="t1")
        mock_conv = MagicMock(id="conv-1")
        msg_assistant = MagicMock(
            content={
                "role": "assistant",
                "tool_calls": [
                    {"id": "call_abc", "function": {"name": "team_status", "arguments": "{}"}},
                    {"id": "call_def", "function": {"name": "list_tasks", "arguments": "{}"}},
                    {"id": "", "function": {"name": "skipped_tool"}},
                ],
            },
        )
        msg_tool = MagicMock(
            content={"role": "tool", "tool_call_id": "call_abc", "content": {}},
        )
        msg_plain = MagicMock(content={})
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.get_conversation = AsyncMock(return_value=mock_conv)
        mock_client.list_messages = AsyncMock(return_value=[msg_assistant, msg_tool, msg_plain])
        mock_client.list_agents = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await conversation_detail(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["tool_call_map"] == {"call_abc": "team_status", "call_def": "list_tasks"}

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import conversation_detail

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await conversation_detail(
            request,
            team_id="x",
            conv_id="conv-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_not_found(self, mock_client):
        from internal.routes.team import conversation_detail

        mock_client.get_team = AsyncMock(return_value=MagicMock())
        mock_client.get_conversation = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await conversation_detail(
            request,
            team_id="t1",
            conv_id="x",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Conversation+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import conversation_detail

        redirect = RedirectResponse(url="/login")
        result = await conversation_detail(
            MagicMock(),
            team_id="t1",
            conv_id="conv-1",
            auth_result=redirect,
        )
        assert result is redirect


class TestConversationDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import conversation_delete

        mock_client.delete_conversation = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await conversation_delete(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import conversation_delete

        mock_client.delete_conversation = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await conversation_delete(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+delete" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import conversation_delete

        redirect = RedirectResponse(url="/login")
        result = await conversation_delete(
            MagicMock(),
            team_id="t1",
            conv_id="conv-1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class TestMemoryList:
    @patch("internal.routes.team.team_client")
    @patch("internal.routes.team.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.team import memory_list

        mock_team = MagicMock(id="t1")
        mock_client.get_team = AsyncMock(return_value=mock_team)
        mock_client.list_memory = AsyncMock(return_value=[])
        mock_client.list_agents = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await memory_list(request, team_id="t1", page=1, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()

    @patch("internal.routes.team.team_client")
    async def test_team_not_found(self, mock_client):
        from internal.routes.team import memory_list

        mock_client.get_team = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await memory_list(request, team_id="x", page=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Team+not+found" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import memory_list

        redirect = RedirectResponse(url="/login")
        result = await memory_list(
            MagicMock(),
            team_id="t1",
            page=1,
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Memory Delete
# ---------------------------------------------------------------------------


class TestMemoryDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import memory_delete

        mock_client.delete_memory = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await memory_delete(
            request,
            team_id="t1",
            memory_id="mem-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Memory+entry+deleted" in result.headers["location"]
        mock_client.delete_memory.assert_awaited_once_with("t1", "mem-1")

    @patch("internal.routes.team.team_client")
    async def test_failure(self, mock_client):
        from internal.routes.team import memory_delete

        mock_client.delete_memory = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await memory_delete(
            request,
            team_id="t1",
            memory_id="mem-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+delete" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import memory_delete

        redirect = RedirectResponse(url="/login")
        result = await memory_delete(
            MagicMock(),
            team_id="t1",
            memory_id="mem-1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Memory Bulk Delete
# ---------------------------------------------------------------------------


class TestMemoryBulkDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import memory_bulk_delete

        mock_client.delete_memory = AsyncMock(return_value=True)
        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["mem-1", "mem-2"]
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await memory_bulk_delete(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=2" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_partial_failure(self, mock_client):
        from internal.routes.team import memory_bulk_delete

        mock_client.delete_memory = AsyncMock(side_effect=[True, False])
        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["mem-1", "mem-2"]
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await memory_bulk_delete(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=1" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_empty_selection(self, mock_client):
        from internal.routes.team import memory_bulk_delete

        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await memory_bulk_delete(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=No+entries+selected" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import memory_bulk_delete

        redirect = RedirectResponse(url="/login")
        result = await memory_bulk_delete(
            MagicMock(),
            team_id="t1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Bulk Delete Conversations
# ---------------------------------------------------------------------------


class TestConversationsBulkDelete:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import conversations_bulk_delete

        mock_client.delete_conversation = AsyncMock(return_value=True)
        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["conv-1", "conv-2"]
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await conversations_bulk_delete(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=2" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_partial_failure(self, mock_client):
        from internal.routes.team import conversations_bulk_delete

        mock_client.delete_conversation = AsyncMock(side_effect=[True, False])
        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["conv-1", "conv-2"]
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await conversations_bulk_delete(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=1" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_empty_selection(self, mock_client):
        from internal.routes.team import conversations_bulk_delete

        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await conversations_bulk_delete(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=No+conversations+selected" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import conversations_bulk_delete

        redirect = RedirectResponse(url="/login")
        result = await conversations_bulk_delete(
            MagicMock(),
            team_id="t1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Cancel Task
# ---------------------------------------------------------------------------


class TestConversationCancelTask:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import conversation_cancel_task

        mock_conv = MagicMock(slug="task-abc123")
        mock_client.get_conversation = AsyncMock(return_value=mock_conv)
        mock_client.cancel_task = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await conversation_cancel_task(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Task+cancelled" in result.headers["location"]
        mock_client.cancel_task.assert_awaited_once_with("t1", "abc123")

    @patch("internal.routes.team.team_client")
    async def test_conversation_not_found(self, mock_client):
        from internal.routes.team import conversation_cancel_task

        mock_client.get_conversation = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await conversation_cancel_task(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Conversation+not+found" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_no_task_linked(self, mock_client):
        from internal.routes.team import conversation_cancel_task

        mock_conv = MagicMock(slug="general-conv")
        mock_client.get_conversation = AsyncMock(return_value=mock_conv)
        user = _make_user()
        request = _make_request()

        result = await conversation_cancel_task(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=No+task+linked" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_cancel_failure(self, mock_client):
        from internal.routes.team import conversation_cancel_task

        mock_conv = MagicMock(slug="task-abc123")
        mock_client.get_conversation = AsyncMock(return_value=mock_conv)
        mock_client.cancel_task = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await conversation_cancel_task(
            request,
            team_id="t1",
            conv_id="conv-1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+cancel+task" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import conversation_cancel_task

        redirect = RedirectResponse(url="/login")
        result = await conversation_cancel_task(
            MagicMock(),
            team_id="t1",
            conv_id="conv-1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Bulk Cancel Tasks
# ---------------------------------------------------------------------------


class TestConversationsBulkCancel:
    @patch("internal.routes.team.team_client")
    async def test_success(self, mock_client):
        from internal.routes.team import conversations_bulk_cancel

        mock_conv1 = MagicMock(slug="task-abc")
        mock_conv2 = MagicMock(slug="task-def")
        mock_client.get_conversation = AsyncMock(side_effect=[mock_conv1, mock_conv2])
        mock_client.cancel_task = AsyncMock(return_value=True)
        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["conv-1", "conv-2"]
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await conversations_bulk_cancel(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=2" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_skips_non_task_conversations(self, mock_client):
        from internal.routes.team import conversations_bulk_cancel

        mock_conv = MagicMock(slug="general-conv")
        mock_client.get_conversation = AsyncMock(return_value=mock_conv)
        mock_client.cancel_task = AsyncMock(return_value=True)
        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["conv-1"]
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await conversations_bulk_cancel(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=0" in result.headers["location"]
        mock_client.cancel_task.assert_not_awaited()

    @patch("internal.routes.team.team_client")
    async def test_skips_missing_conversations(self, mock_client):
        from internal.routes.team import conversations_bulk_cancel

        mock_client.get_conversation = AsyncMock(return_value=None)
        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["conv-1"]
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await conversations_bulk_cancel(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=0" in result.headers["location"]

    @patch("internal.routes.team.team_client")
    async def test_empty_selection(self, mock_client):
        from internal.routes.team import conversations_bulk_cancel

        user = _make_user()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        request = _make_request()
        request.form = AsyncMock(return_value=form_mock)

        result = await conversations_bulk_cancel(
            request,
            team_id="t1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=No+conversations+selected" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.team import conversations_bulk_cancel

        redirect = RedirectResponse(url="/login")
        result = await conversations_bulk_cancel(
            MagicMock(),
            team_id="t1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Extract Task ID helper
# ---------------------------------------------------------------------------


class TestExtractTaskId:
    def test_task_slug(self):
        from internal.routes.team import _extract_task_id

        assert _extract_task_id("task-abc123") == "abc123"

    def test_non_task_slug(self):
        from internal.routes.team import _extract_task_id

        assert _extract_task_id("general-conv") is None

    def test_empty_slug(self):
        from internal.routes.team import _extract_task_id

        assert _extract_task_id("") is None
