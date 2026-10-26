# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the chat orchestration feature."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.chat.orchestrator import ChatOrchestrator
from backend.chat.stream import stream_chat_response
from behave import given, then, when


def _names(text):
    return [name.strip() for name in text.split(",") if name.strip()]


@given('an orchestrator whose conversation "{conversation_id}" has no history')
def step_orchestrator(context, conversation_id):
    for name in ("OpenAIClient", "ChatService", "KnowledgeBase", "PromptService"):
        patcher = patch(f"backend.chat.orchestrator.{name}")
        patcher.start()
        context.patches[name] = patcher

    orchestrator = ChatOrchestrator(context.db)
    conversation = SimpleNamespace(id=uuid.UUID(conversation_id), summary=None)
    orchestrator.chat_service.get_or_create_conversation = AsyncMock(
        return_value=(conversation, False)
    )
    orchestrator.chat_service.get_conversation_history = AsyncMock(return_value=[])
    orchestrator.chat_service.add_message = AsyncMock()
    orchestrator.prompt_service.get_prompt_for_scopes = AsyncMock(return_value="Be helpful")
    orchestrator._try_execute_tools = AsyncMock(return_value=[])
    orchestrator._update_title_background = AsyncMock()
    orchestrator._update_summary_background = AsyncMock()
    context.orchestrator = orchestrator
    context.usage = {"prompt_tokens": 0, "completion_tokens": 0}
    context.tokens = []


@given("no tool applies to the message")
def step_no_tool(context):
    context.orchestrator._try_execute_tools.return_value = []


@given('the tool "{name}" answers "{data}"')
def step_tool(context, name, data):
    context.orchestrator._try_execute_tools.return_value = [
        {"tool": name, "success": True, "data": data, "error": None, "save_in_history": True}
    ]


@given('the model streams the tokens "{tokens}"')
def step_tokens(context, tokens):
    context.tokens = [token.strip('"') for token in tokens.split('", "')]
    _install_stream(context)


@given(
    'the model streams the tokens "{token}" and reports {prompt:d} prompt tokens '
    "and {completion:d} completion tokens"
)
def step_tokens_usage(context, token, prompt, completion):
    context.tokens = [token]
    context.usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    _install_stream(context)


def _install_stream(context):
    async def fake_stream(messages, **kwargs):
        context.model_messages = messages
        for token in context.tokens:
            yield {"type": "token", "content": token}
        yield {"type": "usage", **context.usage}

    context.orchestrator.client.stream = fake_stream


@given("the model fails while streaming")
def step_failure(context):
    async def failing_stream(messages, **kwargs):
        raise RuntimeError("model unavailable")
        yield  # pragma: no cover

    context.orchestrator.client.stream = failing_stream


async def _collect(generator):
    return [event async for event in generator]


def _stream(context, message):
    return context.orchestrator.process_message_stream(
        message, session_id="abcdef12-3456-7890-abcd-ef1234567890"
    )


@when('the user "{message}" is processed as the session "{session_id}"')
def step_process(context, message, session_id):
    generator = context.orchestrator.process_message_stream(message, session_id=session_id)
    context.events = asyncio.run(_collect(generator))


@when('the user "{message}" is processed and converted to SSE')
def step_process_sse(context, message):
    async def run():
        return "".join([chunk async for chunk in stream_chat_response(_stream(context, message))])

    context.sse = asyncio.run(run())


@then('the event types should be "{types}"')
def step_types(context, types):
    assert [event["type"] for event in context.events] == _names(types), context.events


@then('the intent should be "{intent}"')
def step_intent(context, intent):
    (event,) = [e for e in context.events if e["type"] == "intent"]
    assert event["intent"] == intent


@then('the streamed answer should be "{answer}"')
def step_answer(context, answer):
    streamed = "".join(e["content"] for e in context.events if e["type"] == "token")
    assert streamed == answer


@then('the stored messages should be "{messages}"')
def step_stored(context, messages):
    stored = [
        f"{call.args[1]}: {call.args[2]}"
        for call in context.orchestrator.chat_service.add_message.await_args_list
    ]
    assert stored == _names(messages), stored


@then('the model context should mention "{text}"')
def step_context(context, text):
    system_messages = [m["content"] for m in context.model_messages if m["role"] == "system"]
    assert any(text in content for content in system_messages), system_messages


@then("the final event should report {prompt:d} prompt tokens and {completion:d} completion tokens")
def step_final(context, prompt, completion):
    done = context.events[-1]
    assert done["type"] == "done"
    assert done["usage"] == {"prompt_tokens": prompt, "completion_tokens": completion}


@then('the SSE body should contain "{text}"')
def step_sse(context, text):
    assert text in context.sse, context.sse
