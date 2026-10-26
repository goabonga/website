# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for audiosocket.feature."""

import asyncio
import uuid

from asterisk.audiosocket import AudioSocketServer, AudioSocketSession
from behave import given, then, when
from fakes import (
    PACKET_AUDIO,
    PACKET_ERROR,
    PACKET_HANGUP,
    PACKET_SILENCE,
    PACKET_UUID,
    FakeAsterisk,
    make_packet,
)


@given("an AudioSocket server listening on a free loopback port")
def step_server(context):
    context.sessions = []
    server = AudioSocketServer(host="127.0.0.1", port=0)

    async def handler(session):
        context.sessions.append(session)
        await session.receive_loop()

    server.set_handler(handler)
    context.server = server

    async def start():
        context.tcp_server = await asyncio.start_server(server.handle_connection, "127.0.0.1", 0)
        context.port = context.tcp_server.sockets[0].getsockname()[1]

    context.run(start())

    async def stop():
        context.tcp_server.close()
        await context.tcp_server.wait_closed()

    context.async_cleanups.append(stop)


@when("a client connects and sends a UUID packet")
def step_client_connects(context):
    context.expected_uuid = uuid.uuid4()

    async def connect():
        _, writer = await asyncio.open_connection("127.0.0.1", context.port)
        writer.write(make_packet(PACKET_UUID, context.expected_uuid.bytes))
        await writer.drain()
        for _ in range(50):
            if context.sessions and context.sessions[0].channel_uuid:
                break
            await asyncio.sleep(0.01)
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.02)

    context.run(connect())


@then("the handler should receive a session carrying that UUID")
def step_handler_session(context):
    assert len(context.sessions) == 1
    assert context.sessions[0].channel_uuid == str(context.expected_uuid)


@given("an AudioSocket session connected to a fake Asterisk")
def step_session(context):
    context.asterisk = FakeAsterisk()
    context.session = AudioSocketSession(context.asterisk.reader, context.asterisk.writer)
    context.received_audio = []


@given("an audio callback is registered on the session")
def step_callback(context):
    context.session.set_audio_callback(context.received_audio.append)


def _run_receive_loop(context):
    context.run(asyncio.wait_for(context.session.receive_loop(), timeout=2))


@when("Asterisk sends a UUID packet and closes the stream")
def step_send_uuid(context):
    context.expected_uuid = uuid.uuid4()
    context.asterisk.send(PACKET_UUID, context.expected_uuid.bytes)
    context.asterisk.close()
    _run_receive_loop(context)


@when("Asterisk sends an audio packet of {size:d} bytes and closes the stream")
def step_send_audio(context, size):
    context.asterisk.send(PACKET_AUDIO, b"\x01" * size)
    context.asterisk.close()
    _run_receive_loop(context)


@when("Asterisk sends a silence packet and closes the stream")
def step_send_silence(context):
    context.asterisk.send(PACKET_SILENCE)
    context.asterisk.close()
    _run_receive_loop(context)


@when("Asterisk sends a hangup packet")
def step_send_hangup(context):
    context.asterisk.send(PACKET_HANGUP)
    _run_receive_loop(context)


@when('Asterisk sends an error packet saying "{message}"')
def step_send_error(context, message):
    context.asterisk.send(PACKET_ERROR, message.encode())
    _run_receive_loop(context)


@when("Asterisk drops the connection")
def step_drop(context):
    context.asterisk.close()
    _run_receive_loop(context)


@when("the bot sends a frame of {size:d} bytes")
def step_bot_frame(context, size):
    context.run(context.session.send_audio_frame(b"\x02" * size))


@when("the bot sends {size:d} bytes of audio")
def step_bot_audio(context, size):
    context.run(context.session.send_audio(b"\x02" * size))


@when("the bot sends a hangup")
def step_bot_hangup(context):
    context.run(context.session.send_hangup())


@then("the session should store the UUID")
def step_uuid_stored(context):
    assert context.session.channel_uuid == str(context.expected_uuid)


@then("the audio callback should receive {size:d} bytes")
def step_callback_received(context, size):
    assert [len(chunk) for chunk in context.received_audio] == [size]


@then("the audio callback should not be called")
def step_callback_silent(context):
    assert context.received_audio == []


@then("Asterisk should receive one audio packet with a {size:d}-byte payload")
def step_one_packet(context, size):
    packets = context.asterisk.writer.packets()
    assert len(packets) == 1
    assert packets[0][0] == PACKET_AUDIO
    assert len(packets[0][1]) == size


@then("Asterisk should receive {count:d} audio packets with a {size:d}-byte payload")
def step_n_packets(context, count, size):
    packets = context.asterisk.writer.packets()
    assert len(packets) == count
    assert all(kind == PACKET_AUDIO and len(body) == size for kind, body in packets)


@then("Asterisk should receive a hangup packet")
def step_hangup_received(context):
    assert context.asterisk.writer.packets() == [(PACKET_HANGUP, b"")]


@then("the session should be inactive")
def step_inactive(context):
    assert context.session.is_active is False
