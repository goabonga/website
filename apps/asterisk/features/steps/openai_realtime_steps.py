# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for openai_realtime.feature."""

import base64
import json
from unittest.mock import AsyncMock, patch

from asterisk.openai_realtime import OpenAIRealtimeClient
from behave import given, then, when
from fakes import FakeRealtimeSocket

SYSTEM_PROMPT = "You are a test assistant."


def _connect(context):
    """Connect the scenario's client to its fake server."""
    with patch(
        "asterisk.openai_realtime.websockets.connect",
        new=AsyncMock(return_value=context.socket),
    ) as connect:
        context.run(context.client.connect())
        context.connect_mock = connect
    context.async_cleanups.append(_disconnect_quietly(context))


def _disconnect_quietly(context):
    async def cleanup():
        if context.client.is_connected:
            await context.client.disconnect()

    return cleanup


def _sent(context, message_type):
    return [m for m in context.socket.sent if m["type"] == message_type]


def _session(context):
    return _sent(context, "session.update")[0]["session"]


@given("a fake OpenAI Realtime server")
def step_fake_server(context):
    context.socket = FakeRealtimeSocket()
    context.client = OpenAIRealtimeClient(api_key="sk-test", system_prompt=SYSTEM_PROMPT)


@given('the client has a custom tool named "{name}"')
def step_custom_tool(context, name):
    context.client.tools = [{"type": "function", "name": name, "parameters": {}}]


@given("a connected client")
def step_connected(context):
    step_fake_server(context)
    _connect(context)


@given("an audio callback is registered")
def step_audio_callback(context):
    context.audio = []
    context.client.set_audio_callback(context.audio.append)


@given("a transcript callback is registered")
def step_transcript_callback(context):
    context.transcripts = []
    context.client.set_transcript_callback(context.transcripts.append)


@given("an interrupt callback is registered")
def step_interrupt_callback(context):
    context.interrupts = []
    context.client.set_interrupt_callback(lambda: context.interrupts.append(True))


@given('a tool call callback returning "{value}"')
def step_tool_callback_value(context, value):
    context.tool_calls = []

    def callback(name, arguments):
        context.tool_calls.append((name, arguments))
        return {"answer": value}

    context.client.set_tool_call_callback(callback)


@given("a tool call callback returning nothing")
def step_tool_callback_none(context):
    context.tool_calls = []

    def callback(name, arguments):
        context.tool_calls.append((name, arguments))

    context.client.set_tool_call_callback(callback)


@when("the client connects")
def step_connect(context):
    _connect(context)


@when("the client sends {size:d} bytes of PCM audio")
def step_send_audio(context, size):
    context.pcm = b"\x01\x02" * (size // 2)
    context.run(context.client.send_audio(context.pcm))


@when('the client sends the text "{text}"')
def step_send_text(context, text):
    context.run(context.client.send_text(text))


@when("OpenAI sends an audio delta")
def step_audio_delta(context):
    context.pcm = b"\x05\x06" * 100
    context.socket.receive(
        {"type": "response.audio.delta", "delta": base64.b64encode(context.pcm).decode()}
    )
    context.run(context.socket.settle())


@when('OpenAI sends the transcript "{text}"')
def step_transcript(context, text):
    context.socket.receive(
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": text}
    )
    context.run(context.socket.settle())


@when('OpenAI calls the tool "{name}"')
def step_tool_call(context, name):
    context.socket.receive(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "call-1",
            "name": name,
            "arguments": json.dumps({"query": "opening hours"}),
        }
    )
    context.run(context.socket.settle())


@when("OpenAI starts a response")
def step_response_started(context):
    context.socket.receive({"type": "response.created"})
    context.run(context.socket.settle())


@when("OpenAI finishes the response")
def step_response_done(context):
    context.socket.receive({"type": "response.done"})
    context.run(context.socket.settle())


@when("OpenAI detects speech from the caller")
def step_speech_started(context):
    context.socket.receive({"type": "input_audio_buffer.speech_started"})
    context.run(context.socket.settle())


@when("the client disconnects")
def step_disconnect(context):
    context.run(context.client.disconnect())


@then("the client should be connected with an authorization header")
def step_check_connected(context):
    assert context.client.is_connected
    args, kwargs = context.connect_mock.call_args
    assert "model=" in args[0]
    assert kwargs["additional_headers"]["Authorization"] == "Bearer sk-test"


@then("a session.update message should have been sent")
def step_session_update(context):
    assert len(_sent(context, "session.update")) == 1


@then("the session should use server-side voice activity detection")
def step_vad(context):
    assert _session(context)["turn_detection"]["type"] == "server_vad"


@then("the session should declare the hangup tool")
def step_hangup_tool(context):
    assert "hangup" in [tool["name"] for tool in _session(context)["tools"]]


@then("the session should carry the system prompt")
def step_system_prompt(context):
    assert _session(context)["instructions"] == SYSTEM_PROMPT


@then('the session should declare the tools "{names}"')
def step_declared_tools(context, names):
    declared = [tool["name"] for tool in _session(context)["tools"]]
    assert declared == [name.strip() for name in names.split(",")]


@then("an input_audio_buffer.append message should carry the base64 audio")
def step_audio_message(context):
    (message,) = _sent(context, "input_audio_buffer.append")
    assert base64.b64decode(message["audio"]) == context.pcm


@then("the audio callback should receive the decoded PCM bytes")
def step_audio_received(context):
    assert context.audio == [context.pcm]


@then('the transcript callback should receive "{text}"')
def step_transcript_received(context, text):
    assert context.transcripts == [text]


@then('a user message with the text "{text}" should have been sent')
def step_user_message(context, text):
    (message,) = _sent(context, "conversation.item.create")
    assert message["item"]["role"] == "user"
    assert message["item"]["content"][0]["text"] == text


@then("a response.create message should follow")
def step_response_create(context):
    assert _sent(context, "response.create")


@then("no response.create message should follow")
def step_no_response_create(context):
    assert not _sent(context, "response.create")


@then("the tool callback should receive the tool name and arguments")
def step_tool_callback_received(context):
    assert context.tool_calls == [("search_knowledge", {"query": "opening hours"})]


@then("a function_call_output with the result should have been sent")
def step_function_output(context):
    (message,) = _sent(context, "conversation.item.create")
    assert message["item"]["type"] == "function_call_output"
    assert message["item"]["call_id"] == "call-1"
    assert json.loads(message["item"]["output"]) == {"answer": "found"}


@then("a function_call_output reporting success should have been sent")
def step_function_output_success(context):
    (message,) = _sent(context, "conversation.item.create")
    assert json.loads(message["item"]["output"]) == {"success": True}


@then("a response.cancel message should have been sent")
def step_cancel_sent(context):
    assert _sent(context, "response.cancel")


@then("the interrupt callback should have been called")
def step_interrupt_called(context):
    assert context.interrupts == [True]


@then("the client should be responding")
def step_responding(context):
    assert context.client.is_responding


@then("the client should not be responding")
def step_not_responding(context):
    assert not context.client.is_responding


@then("the WebSocket should be closed")
def step_ws_closed(context):
    assert context.socket.closed


@then("the client should be marked as disconnected")
def step_marked_disconnected(context):
    assert not context.client.is_connected
