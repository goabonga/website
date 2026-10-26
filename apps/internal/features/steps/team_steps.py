# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for team feature tests.

Uses MagicMock objects to simulate Pydantic models returned by team_client.
All team_client methods are async, so we configure return_value on the mock
(MagicMock auto-handles awaiting).
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from behave import given

# ---------------------------------------------------------------------------
# Mock factory helpers
# ---------------------------------------------------------------------------


def _make_team(**kwargs):
    """Create a mock team object with attribute access."""
    team = MagicMock()
    team.id = kwargs.get("id", "team-1")
    team.name = kwargs.get("name", "Test Team")
    team.slug = kwargs.get("slug", "test-team")
    team.description = kwargs.get("description", "A test team")
    team.is_active = kwargs.get("is_active", True)
    team.config = kwargs.get("config", {})
    team.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    team.updated_at = kwargs.get("updated_at", datetime(2024, 1, 1))
    return team


def _make_agent(**kwargs):
    """Create a mock agent object."""
    agent = MagicMock()
    agent.id = kwargs.get("id", "agent-1")
    agent.team_id = kwargs.get("team_id", "team-1")
    agent.name = kwargs.get("name", "Test Agent")
    agent.role = kwargs.get("role", "assistant")
    agent.description = kwargs.get("description", "A test agent")
    agent.system_prompt = kwargs.get("system_prompt", "You are helpful.")
    agent.model = kwargs.get("model", "gpt-4o")
    agent.provider = kwargs.get("provider", "openai")
    agent.is_active = kwargs.get("is_active", True)
    agent.config = kwargs.get("config", {})
    agent.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    return agent


def _make_workflow(**kwargs):
    """Create a mock workflow object."""
    wf = MagicMock()
    wf.id = kwargs.get("id", "wf-1")
    wf.team_id = kwargs.get("team_id", "team-1")
    wf.name = kwargs.get("name", "Test Workflow")
    wf.description = kwargs.get("description", "A test workflow")
    wf.steps = kwargs.get("steps", {})
    wf.status = kwargs.get("status", "draft")
    wf.config = kwargs.get("config", {})
    wf.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    return wf


def _make_conversation(**kwargs):
    """Create a mock conversation object."""
    conv = MagicMock()
    conv.id = kwargs.get("id", "conv-1")
    conv.slug = kwargs.get("slug", "test-conv")
    conv.title = kwargs.get("title", "Test Conversation")
    conv.type = kwargs.get("type", "general")
    conv.status = kwargs.get("status", "active")
    conv.extra = kwargs.get("extra", {})
    conv.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    conv.updated_at = kwargs.get("updated_at", datetime(2024, 1, 1))
    return conv


def _make_message(**kwargs):
    """Create a mock message object."""
    msg = MagicMock()
    msg.id = kwargs.get("id", "msg-1")
    msg.conversation_id = kwargs.get("conversation_id", "conv-1")
    msg.agent_id = kwargs.get("agent_id", "agent-100000001")
    msg.type = kwargs.get("type", "message")
    msg.content = kwargs.get("content", {})
    msg.text = kwargs.get("text", "Hello, world!")
    msg.visibility = kwargs.get("visibility", "public")
    msg.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    return msg


def _make_memory(**kwargs):
    """Create a mock memory entry object."""
    mem = MagicMock()
    mem.id = kwargs.get("id", "mem-1")
    mem.team_id = kwargs.get("team_id", "team-1")
    mem.agent_id = kwargs.get("agent_id")
    mem.conversation_id = kwargs.get("conversation_id")
    mem.content = kwargs.get("content", "Important fact")
    mem.extra = kwargs.get("extra", {})
    mem.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    return mem


# ---------------------------------------------------------------------------
# Dashboard steps
# ---------------------------------------------------------------------------


@given("the team list returns data")
def step_team_list(context):
    mock = context.mock_team
    mock.list_teams = AsyncMock(return_value=[_make_team()])


# ---------------------------------------------------------------------------
# Team steps
# ---------------------------------------------------------------------------


@given('a team exists with id "{team_id}"')
def step_team_exists(context, team_id):
    mock = context.mock_team
    mock.get_team = AsyncMock(return_value=_make_team(id=team_id))
    # Default empty lists for detail view sub-resources
    mock.list_agents = AsyncMock(return_value=[])
    mock.list_workflows = AsyncMock(return_value=[])
    mock.list_memory = AsyncMock(return_value=[])
    mock.list_conversations = AsyncMock(return_value=[])


@given("a team does not exist")
def step_team_not_exists(context):
    mock = context.mock_team
    mock.get_team = AsyncMock(return_value=None)


@given("creating a team succeeds")
def step_create_team_succeeds(context):
    mock = context.mock_team
    mock.create_team = AsyncMock(return_value=_make_team(id="team-new"))


@given("creating a team fails")
def step_create_team_fails(context):
    mock = context.mock_team
    mock.create_team = AsyncMock(return_value=None)


@given("updating a team succeeds")
def step_update_team_succeeds(context):
    mock = context.mock_team
    mock.update_team = AsyncMock(return_value=_make_team())


@given("updating a team fails")
def step_update_team_fails(context):
    mock = context.mock_team
    mock.update_team = AsyncMock(return_value=None)


@given("deleting a team succeeds")
def step_delete_team_succeeds(context):
    mock = context.mock_team
    mock.delete_team = AsyncMock(return_value=True)


@given("deleting a team fails")
def step_delete_team_fails(context):
    mock = context.mock_team
    mock.delete_team = AsyncMock(return_value=False)


# ---------------------------------------------------------------------------
# Agent steps
# ---------------------------------------------------------------------------


@given('the team agents list returns data for team "{team_id}"')
def step_agents_list(context, team_id):
    mock = context.mock_team
    mock.list_agents = AsyncMock(return_value=[_make_agent(team_id=team_id)])


@given('a team agent exists with id "{agent_id}" for team "{team_id}"')
def step_agent_exists(context, agent_id, team_id):
    mock = context.mock_team
    mock.get_agent = AsyncMock(return_value=_make_agent(id=agent_id, team_id=team_id))


@given('a team agent does not exist for team "{team_id}"')
def step_agent_not_exists(context, team_id):
    mock = context.mock_team
    mock.get_agent = AsyncMock(return_value=None)


@given('creating a team agent succeeds for team "{team_id}"')
def step_create_agent_succeeds(context, team_id):
    mock = context.mock_team
    mock.create_agent = AsyncMock(return_value=_make_agent(id="agent-new", team_id=team_id))


@given('creating a team agent fails for team "{team_id}"')
def step_create_agent_fails(context, team_id):
    mock = context.mock_team
    mock.create_agent = AsyncMock(return_value=None)


@given('updating a team agent succeeds for team "{team_id}"')
def step_update_agent_succeeds(context, team_id):
    mock = context.mock_team
    mock.update_agent = AsyncMock(return_value=_make_agent(team_id=team_id))


@given('updating a team agent fails for team "{team_id}"')
def step_update_agent_fails(context, team_id):
    mock = context.mock_team
    mock.update_agent = AsyncMock(return_value=None)


@given('deleting a team agent succeeds for team "{team_id}"')
def step_delete_agent_succeeds(context, team_id):
    mock = context.mock_team
    mock.delete_agent = AsyncMock(return_value=True)


@given('deleting a team agent fails for team "{team_id}"')
def step_delete_agent_fails(context, team_id):
    mock = context.mock_team
    mock.delete_agent = AsyncMock(return_value=False)


# ---------------------------------------------------------------------------
# Workflow steps
# ---------------------------------------------------------------------------


@given('the team workflows list returns data for team "{team_id}"')
def step_workflows_list(context, team_id):
    mock = context.mock_team
    mock.list_workflows = AsyncMock(return_value=[_make_workflow(team_id=team_id)])


@given('a team workflow exists with id "{workflow_id}" for team "{team_id}"')
def step_workflow_exists(context, workflow_id, team_id):
    mock = context.mock_team
    # workflow_edit uses list_workflows and filters by id
    mock.list_workflows = AsyncMock(return_value=[_make_workflow(id=workflow_id, team_id=team_id)])


@given('a team workflow does not exist for team "{team_id}"')
def step_workflow_not_exists(context, team_id):
    mock = context.mock_team
    mock.list_workflows = AsyncMock(return_value=[])


@given('creating a team workflow succeeds for team "{team_id}"')
def step_create_workflow_succeeds(context, team_id):
    mock = context.mock_team
    mock.create_workflow = AsyncMock(return_value=_make_workflow(id="wf-new", team_id=team_id))


@given('creating a team workflow fails for team "{team_id}"')
def step_create_workflow_fails(context, team_id):
    mock = context.mock_team
    mock.create_workflow = AsyncMock(return_value=None)


@given('updating a team workflow succeeds for team "{team_id}"')
def step_update_workflow_succeeds(context, team_id):
    mock = context.mock_team
    mock.update_workflow = AsyncMock(return_value=_make_workflow(team_id=team_id))


@given('updating a team workflow fails for team "{team_id}"')
def step_update_workflow_fails(context, team_id):
    mock = context.mock_team
    mock.update_workflow = AsyncMock(return_value=None)


@given('deleting a team workflow succeeds for team "{team_id}"')
def step_delete_workflow_succeeds(context, team_id):
    mock = context.mock_team
    mock.delete_workflow = AsyncMock(return_value=True)


@given('deleting a team workflow fails for team "{team_id}"')
def step_delete_workflow_fails(context, team_id):
    mock = context.mock_team
    mock.delete_workflow = AsyncMock(return_value=False)


# ---------------------------------------------------------------------------
# Conversation steps
# ---------------------------------------------------------------------------


@given("the team conversations list returns data")
def step_conversations_list(context):
    mock = context.mock_team
    mock.list_conversations = AsyncMock(return_value=[_make_conversation()])


@given('a team conversation exists with id "{conv_id}"')
def step_conversation_exists(context, conv_id):
    mock = context.mock_team
    mock.get_conversation = AsyncMock(return_value=_make_conversation(id=conv_id))
    mock.list_messages = AsyncMock(return_value=[_make_message()])


@given("a team conversation does not exist")
def step_conversation_not_exists(context):
    mock = context.mock_team
    mock.get_conversation = AsyncMock(return_value=None)


@given("deleting a team conversation succeeds")
def step_delete_conversation_succeeds(context):
    mock = context.mock_team
    mock.delete_conversation = AsyncMock(return_value=True)


@given("deleting a team conversation fails")
def step_delete_conversation_fails(context):
    mock = context.mock_team
    mock.delete_conversation = AsyncMock(return_value=False)


# ---------------------------------------------------------------------------
# Memory steps
# ---------------------------------------------------------------------------


@given('the team memory list returns data for team "{team_id}"')
def step_memory_list(context, team_id):
    mock = context.mock_team
    mock.list_memory = AsyncMock(return_value=[_make_memory(team_id=team_id)])
