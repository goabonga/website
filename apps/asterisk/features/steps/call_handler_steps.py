# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for call_handler.feature."""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, patch

import numpy as np
from asterisk import call_handler
from asterisk.audiosocket import AudioSocketSession
from asterisk.config import config
from behave import given, then, when
from fakes import PACKET_AUDIO, PACKET_HANGUP, FakeAsterisk, FakeRealtimeSocket


def _wait_until(context, predicate, timeout=3.0):
    async def poll():
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not predicate():
            assert loop.time() < deadline, "condition not reached in time"
            await asyncio.sleep(0.01)

    context.run(poll())


def _sleep(context, seconds):
    context.run(asyncio.sleep(seconds))


def _tone_24k(samples=480):
    t = np.arange(samples) / 24000
    return (np.sin(2 * np.pi * 440 * t) * 16000).astype("<i2").tobytes()


def _audio_packets(context):
    return [body for kind, body in context.asterisk.writer.packets() if kind == PACKET_AUDIO]


async def _finish_call(context):
    task = getattr(context, "call_task", None)
    if task is None or task.done():
        return
    context.asterisk.send(PACKET_HANGUP)
    try:
        await asyncio.wait_for(task, timeout=3)
    except TimeoutError:
        task.cancel()


@given("a fake Asterisk call")
def step_fake_call(context):
    context.asterisk = FakeAsterisk()
    context.session = AudioSocketSession(context.asterisk.reader, context.asterisk.writer)
    context.async_cleanups.append(lambda: _finish_call(context))


@given("OpenAI Realtime answering through a fake server")
def step_fake_server(context):
    context.socket = FakeRealtimeSocket()
    patcher = patch(
        "asterisk.openai_realtime.websockets.connect",
        new=AsyncMock(return_value=context.socket),
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('the bot is configured with voice "{voice}" and prompt "{prompt}"')
def step_configure(context, voice, prompt):
    for name, value in (("OPENAI_VOICE", voice), ("OPENAI_SYSTEM_PROMPT", prompt)):
        patcher = patch.object(config, name, value)
        patcher.start()
        context.add_cleanup(patcher.stop)


@when("the call is handled")
def step_handle_call(context):
    context.call_task = context.loop.create_task(call_handler.handle_call(context.session))
    # The greeting is requested once the OpenAI session is established.
    _wait_until(context, lambda: "response.create" in context.socket.sent_types())


@when("Asterisk sends {count:d} audio frames of {size:d} bytes")
def step_caller_audio(context, count, size):
    for _ in range(count):
        context.asterisk.send(PACKET_AUDIO, b"\x01\x00" * (size // 2))
    _wait_until(
        context,
        lambda: any(m["type"] == "input_audio_buffer.append" for m in context.socket.sent),
    )


@when("Asterisk sends {count:d} loud audio frames")
def step_loud_audio(context, count):
    loud = np.full(160, 5000, dtype="<i2").tobytes()
    for _ in range(count):
        context.asterisk.send(PACKET_AUDIO, loud)
    _wait_until(context, lambda: "response.cancel" in context.socket.sent_types())


@when("OpenAI sends 20 ms of audio")
def step_model_audio(context):
    context.socket.receive(
        {"type": "response.audio.delta", "delta": base64.b64encode(_tone_24k()).decode()}
    )
    _wait_until(context, lambda: any(any(frame) for frame in _audio_packets(context)))


@when("{ms:d} ms pass without model audio")
def step_pass_time(context, ms):
    _sleep(context, ms / 1000)


@when("the model starts speaking")
def step_response_started(context):
    context.socket.receive({"type": "response.created"})
    context.run(context.socket.settle())


@when("OpenAI calls the hangup tool")
def step_hangup_tool(context):
    context.socket.receive(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "call-1",
            "name": "hangup",
            "arguments": json.dumps({"reason": "user_goodbye"}),
        }
    )
    _wait_until(context, lambda: context.call_task.done(), timeout=5)


@when("Asterisk hangs up")
def step_asterisk_hangs_up(context):
    context.asterisk.send(PACKET_HANGUP)
    _wait_until(context, lambda: context.call_task.done(), timeout=5)


@then('the OpenAI session should use voice "{voice}" and prompt "{prompt}"')
def step_session_config(context, voice, prompt):
    session = next(m for m in context.socket.sent if m["type"] == "session.update")["session"]
    assert session["voice"] == voice
    assert session["instructions"] == prompt


@then("a greeting request should have been sent to OpenAI")
def step_greeting(context):
    item = next(m for m in context.socket.sent if m["type"] == "conversation.item.create")
    assert item["item"]["content"][0]["text"] == call_handler.GREETING_MESSAGE


@then("OpenAI should receive {size:d} bytes of 24 kHz audio")
def step_openai_audio(context, size):
    chunks = [m for m in context.socket.sent if m["type"] == "input_audio_buffer.append"]
    assert [len(base64.b64decode(m["audio"])) for m in chunks] == [size]


@then("Asterisk should receive a non-silent 320-byte audio frame")
def step_played_frame(context):
    frames = _audio_packets(context)
    assert all(len(frame) == 320 for frame in frames)
    assert any(any(frame) for frame in frames)


@then("Asterisk should receive only silent frames")
def step_silent_frames(context):
    frames = _audio_packets(context)
    assert frames
    assert not any(any(frame) for frame in frames)


@then("OpenAI should have been asked to cancel the response")
def step_cancel_requested(context):
    assert "response.cancel" in context.socket.sent_types()


@then("Asterisk should be told to hang up")
def step_hangup_packet(context):
    kinds = [kind for kind, _ in context.asterisk.writer.packets()]
    assert PACKET_HANGUP in kinds


@then("the call should end")
def step_call_ended(context):
    assert context.call_task.done()
    assert context.call_task.exception() is None
    assert context.session.is_active is False


@then("the OpenAI connection should be closed")
def step_openai_closed(context):
    assert context.socket.closed
