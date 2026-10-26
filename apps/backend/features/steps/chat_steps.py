# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for chat feature."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from backend.database import get_db
from backend.middleware import check_rate_limit_with_context
from backend.session.dependencies import ChatContext
from behave import given, then
from fastapi import HTTPException


@given("the chat API is wired to a mock database")
def step_wire_database(context):
    """Serve the chat routes of the real application with a mocked database session."""
    context.app.dependency_overrides[get_db] = lambda: context.db


@given("I am an anonymous user")
def step_anonymous_user(context):
    """Set up anonymous ChatContext."""
    context.chat_context = ChatContext(
        user_id=None,
        session_id="abcdef12-3456-7890-abcd-ef1234567890",
        is_authenticated=False,
        session_created=False,
        client_ip="127.0.0.1",
    )
    context.app.dependency_overrides[check_rate_limit_with_context] = lambda: context.chat_context
    patcher = patch(
        "backend.routes.chat._migrate_anonymous_session",
        new_callable=AsyncMock,
        return_value=False,
    )
    patcher.start()
    context.patches["migrate_session"] = patcher


@given("I am an authenticated user")
def step_authenticated_user(context):
    """Set up authenticated ChatContext."""
    context.chat_context = ChatContext(
        user_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        session_id=None,
        is_authenticated=True,
        session_created=False,
        client_ip="127.0.0.1",
        access_token="test-jwt-token",
        scopes={"openid", "profile"},
    )
    context.app.dependency_overrides[check_rate_limit_with_context] = lambda: context.chat_context
    patcher = patch(
        "backend.routes.chat._migrate_anonymous_session",
        new_callable=AsyncMock,
        return_value=False,
    )
    patcher.start()
    context.patches["migrate_session"] = patcher


@given("I am a new anonymous user with a freshly created session")
def step_new_session_user(context):
    """Set up anonymous ChatContext with session_created=True."""
    context.chat_context = ChatContext(
        user_id=None,
        session_id="abcdef12-3456-7890-abcd-ef1234567890",
        is_authenticated=False,
        session_created=True,
        client_ip="127.0.0.1",
    )
    context.app.dependency_overrides[check_rate_limit_with_context] = lambda: context.chat_context
    patcher = patch(
        "backend.routes.chat._migrate_anonymous_session",
        new_callable=AsyncMock,
        return_value=False,
    )
    patcher.start()
    context.patches["migrate_session"] = patcher


@given("I am a rate-limited user")
def step_rate_limited_user(context):
    """Override check_rate_limit_with_context to raise 429."""

    async def raise_rate_limit():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": "60"},
        )

    context.app.dependency_overrides[check_rate_limit_with_context] = raise_rate_limit


@given("the chat service returns an empty conversation history")
def step_empty_history(context):
    """Mock ChatService to return empty conversation history."""
    mock_conversation = MagicMock()
    mock_conversation.id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    patcher = patch("backend.routes.chat.ChatService")
    mock_chat_cls = patcher.start()
    context.patches["chat_service"] = patcher

    mock_chat = AsyncMock()
    mock_chat.get_or_create_conversation.return_value = (mock_conversation, False)
    mock_chat.get_conversation_history.return_value = []
    mock_chat_cls.return_value = mock_chat


@given("the chat service returns conversation history:")
def step_conversation_history(context):
    """Mock ChatService to return specified conversation history."""
    messages = [{"role": row["role"], "content": row["content"]} for row in context.table]

    mock_conversation = MagicMock()
    mock_conversation.id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    patcher = patch("backend.routes.chat.ChatService")
    mock_chat_cls = patcher.start()
    context.patches["chat_service"] = patcher

    mock_chat = AsyncMock()
    mock_chat.get_or_create_conversation.return_value = (mock_conversation, False)
    mock_chat.get_conversation_history.return_value = messages
    mock_chat_cls.return_value = mock_chat


@given("the chat orchestrator streams the following events:")
def step_mock_orchestrator_events(context):
    """Mock ChatOrchestrator to yield specified SSE events."""
    events = []
    for row in context.table:
        event_data = json.loads(row["data"])
        event_data["type"] = row["type"]
        events.append(event_data)

    patcher = patch("backend.routes.chat.ChatOrchestrator")
    mock_orch_cls = patcher.start()
    context.patches["orchestrator"] = patcher

    mock_orch = MagicMock()

    async def fake_stream(**kwargs):
        for event in events:
            yield event

    mock_orch.process_message_stream = fake_stream
    mock_orch_cls.return_value = mock_orch


@given("the chat orchestrator streams a minimal response")
def step_mock_orchestrator_minimal(context):
    """Mock ChatOrchestrator with minimal done event."""
    patcher = patch("backend.routes.chat.ChatOrchestrator")
    mock_orch_cls = patcher.start()
    context.patches["orchestrator"] = patcher

    mock_orch = MagicMock()

    async def fake_stream(**kwargs):
        yield {"type": "done", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    mock_orch.process_message_stream = fake_stream
    mock_orch_cls.return_value = mock_orch


@then('the SSE stream should contain an event of type "{event_type}"')
def step_check_sse_event_type(context, event_type):
    """Check that the SSE response body contains an event of the given type."""
    body = context.response.text
    expected = f"event: {event_type}"
    assert expected in body, f"Expected SSE event '{event_type}' not found in body:\n{body[:1000]}"
