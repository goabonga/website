# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-process fakes of the telephony side, shared by the step modules."""

import asyncio
import json
import struct

PACKET_HANGUP = 0x00
PACKET_UUID = 0x01
PACKET_SILENCE = 0x02
PACKET_AUDIO = 0x10
PACKET_ERROR = 0xFF


def make_packet(packet_type: int, payload: bytes = b"") -> bytes:
    """Build an AudioSocket packet: 1-byte type, 2-byte big-endian length, payload."""
    return struct.pack(">BH", packet_type, len(payload)) + payload


class FakeWriter:
    """Stands in for the stream writer connected to Asterisk."""

    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes):
        self.data += data

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None

    def get_extra_info(self, name, default=None):
        return ("127.0.0.1", 40000) if name == "peername" else default

    def packets(self) -> list[tuple[int, bytes]]:
        """Decode everything written so far into (type, payload) tuples."""
        result, data, offset = [], bytes(self.data), 0
        while offset + 3 <= len(data):
            length = struct.unpack(">H", data[offset + 1 : offset + 3])[0]
            result.append((data[offset], data[offset + 3 : offset + 3 + length]))
            offset += 3 + length
        return result


class FakeAsterisk:
    """The Asterisk end of an AudioSocket connection, without any socket."""

    def __init__(self):
        self.reader = asyncio.StreamReader()
        self.writer = FakeWriter()

    def send(self, packet_type: int, payload: bytes = b""):
        """Queue a packet as if Asterisk had written it."""
        self.reader.feed_data(make_packet(packet_type, payload))

    def close(self):
        """Signal end of stream, as when Asterisk drops the connection."""
        self.reader.feed_eof()


class FakeRealtimeSocket:
    """The OpenAI Realtime WebSocket, scripted by the scenario.

    Messages the client sends are recorded in ``sent``. Messages queued with
    ``receive()`` are delivered to the client's receive loop, and ``settle()``
    returns once the client has finished handling all of them.
    """

    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False
        self._incoming: asyncio.Queue = asyncio.Queue()
        self._in_flight = False

    async def send(self, raw: str):
        self.sent.append(json.loads(raw))

    async def close(self):
        self.closed = True
        self._incoming.put_nowait(None)

    def receive(self, message: dict):
        self._incoming.put_nowait(json.dumps(message))

    async def settle(self):
        await asyncio.wait_for(self._incoming.join(), timeout=2)

    def sent_types(self) -> list[str]:
        return [message["type"] for message in self.sent]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._in_flight:
            self._incoming.task_done()
            self._in_flight = False
        item = await self._incoming.get()
        if item is None:
            self._incoming.task_done()
            raise StopAsyncIteration
        self._in_flight = True
        return item
