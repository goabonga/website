# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the conversation feature."""

import asyncio
import uuid
from unittest.mock import MagicMock

from backend.chat.service import ChatService
from backend.models.conversation import Conversation, Message
from behave import given, then, when


def _result(scalar=None, items=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = items or []
    return result


def _conversation(session_id):
    conversation = Conversation(id=uuid.uuid4(), session_id=session_id, user_id=None)
    conversation.messages = []
    return conversation


@when('a conversation is created for the session "{session_id}"')
def step_create(context, session_id):
    service = ChatService(context.db)
    context.conversation = asyncio.run(service.create_conversation(session_id=session_id))


@then("the conversation should be saved and committed")
def step_saved(context):
    context.db.add.assert_called_once_with(context.conversation)
    context.db.commit.assert_awaited_once()


@then('the conversation should belong to the session "{session_id}"')
def step_belongs(context, session_id):
    assert context.conversation.session_id == session_id
    assert context.conversation.user_id is None


@given('the session "{session_id}" already has an active conversation')
def step_existing(context, session_id):
    context.existing = _conversation(session_id)
    context.db.execute.return_value = _result(scalar=context.existing)


@given('the session "{session_id}" has no active conversation')
def step_none(context, session_id):
    context.db.execute.return_value = _result(scalar=None)


@when("the conversation of that session is requested")
def step_get_or_create(context):
    session_id = "abcdef12-3456-7890-abcd-ef1234567890"
    service = ChatService(context.db)
    context.conversation, context.created = asyncio.run(
        service.get_or_create_conversation(session_id=session_id)
    )


@then("the existing conversation should be returned")
def step_existing_returned(context):
    assert context.conversation is context.existing


@then("no new conversation should be created")
def step_not_created(context):
    assert context.created is False
    context.db.add.assert_not_called()


@then("a new conversation should be created")
def step_created(context):
    assert context.created is True
    context.db.add.assert_called_once()


@when('the message "{content}" is added with the role "{role}"')
def step_add_message(context, content, role):
    service = ChatService(context.db)
    context.message = asyncio.run(service.add_message(uuid.uuid4(), role, content))


@then('the stored message should have the role "{role}" and the content "{content}"')
def step_message_stored(context, role, content):
    stored = context.db.add.call_args.args[0]
    assert isinstance(stored, Message)
    assert (stored.role, stored.content) == (role, content)


@given("the conversation contains the messages:")
def step_messages(context):
    messages = [Message(role=row["role"], content=row["content"]) for row in context.table]
    context.db.execute.return_value = _result(items=messages)


@when("the conversation history is requested")
def step_history(context):
    service = ChatService(context.db)
    context.history = asyncio.run(service.get_conversation_history(uuid.uuid4()))


@then("the history should be:")
def step_history_equals(context):
    expected = [{"role": row["role"], "content": row["content"]} for row in context.table]
    assert context.history == expected, context.history


@when("the conversation of that session is archived")
def step_archive(context):
    service = ChatService(context.db)
    context.archived = asyncio.run(
        service.archive_conversation(session_id="abcdef12-3456-7890-abcd-ef1234567890")
    )


@then("the archived conversation should have an archive date")
def step_archived(context):
    assert context.archived is context.existing
    assert context.archived.archived_at is not None
