# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the team AI administration."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from behave import given, then


@given('the agent "{agent_id}" has a skill called "{name}"')
def step_agent_skill(context, agent_id, name):
    skill = MagicMock()
    skill.id = "skill-1"
    skill.agent_id = agent_id
    skill.name = name
    skill.description = "Searches the knowledge base"
    skill.content = ""
    skill.allowed_tools = []
    skill.config = {}
    skill.is_active = True
    skill.created_at = datetime(2024, 1, 1)
    context.mock_team.list_skills = AsyncMock(return_value=[skill])
    context.mock_team.get_skill = AsyncMock(return_value=skill)


@given("{count:d} team conversations exist")
def step_many_team_conversations(context, count):
    conversations = []
    for index in range(count):
        conversation = MagicMock()
        conversation.id = f"conv-{index}"
        conversation.slug = f"conv-{index}"
        conversation.title = f"Conversation {index}"
        conversation.type = "general"
        conversation.status = "active"
        conversation.extra = {}
        conversation.created_at = datetime(2024, 1, 1)
        conversation.updated_at = datetime(2024, 1, 1)
        conversations.append(conversation)
    context.mock_team.list_conversations = AsyncMock(return_value=conversations)
    context.mock_team.get_conversation = AsyncMock(
        side_effect=lambda conv_id: next((c for c in conversations if c.id == conv_id), None)
    )


@given('a team message says "{text}"')
def step_team_message(context, text):
    message = MagicMock()
    message.id = "msg-1"
    message.conversation_id = "conv-1"
    message.agent_id = "agent-100000001"
    message.type = "message"
    message.content = {}
    message.text = text
    message.visibility = "public"
    message.created_at = datetime(2024, 1, 1)
    context.mock_team.list_messages = AsyncMock(return_value=[message])


@given('the team memory holds the entry "{text}"')
def step_team_memory_entry(context, text):
    entry = MagicMock()
    entry.id = "mem-1"
    entry.team_id = "team-1"
    entry.agent_id = None
    entry.conversation_id = None
    entry.content = text
    entry.extra = {}
    entry.created_at = datetime(2024, 1, 1)
    context.mock_team.list_memory = AsyncMock(return_value=[entry])


@then('the team service should have been asked to create the team "{name}"')
def step_team_created(context, name):
    kwargs = context.mock_team.create_team.await_args.kwargs
    assert kwargs["name"] == name, kwargs


@then("the team service should not have been asked to create a team")
def step_no_team_created(context):
    context.mock_team.create_team.assert_not_awaited()


@then('the team service should have been asked to delete the conversations "{ids}"')
def step_conversations_deleted(context, ids):
    deleted = sorted(call.args[0] for call in context.mock_team.delete_conversation.await_args_list)
    assert deleted == sorted(ids.split(",")), deleted


@then('the team service should have been asked to delete the memory entries "{ids}"')
def step_memory_deleted(context, ids):
    deleted = sorted(call.args[1] for call in context.mock_team.delete_memory.await_args_list)
    assert deleted == sorted(ids.split(",")), deleted


@given("launching an agent task succeeds")
def step_launch_succeeds(context):
    context.mock_team.create_task = AsyncMock(return_value=MagicMock(id="task-1"))


@given("launching an agent task fails")
def step_launch_fails(context):
    context.mock_team.create_task = AsyncMock(return_value=None)


@given("deleting a team memory entry succeeds")
def step_delete_memory_succeeds(context):
    context.mock_team.delete_memory = AsyncMock(return_value=True)


@then("the team service should not have been asked to delete a team")
def step_no_team_deleted(context):
    context.mock_team.delete_team.assert_not_awaited()
