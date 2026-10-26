# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-process fakes of the telephony side, shared by the step modules."""

import asyncio
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
