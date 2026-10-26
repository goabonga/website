# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-process fakes of the telephony side, shared by the step modules."""

import asyncio
import hashlib
import json
import math
import struct
from unittest.mock import AsyncMock, MagicMock, patch

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


EMBEDDING_SIZE = 64


def embed(text: str) -> list[float]:
    """Deterministic bag-of-words embedding: similar wording gives similar vectors."""
    vector = [0.0] * EMBEDDING_SIZE
    for word in "".join(c if c.isalnum() else " " for c in text.lower()).split():
        index = int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_SIZE
        vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _parse_vector(text: str) -> list[float]:
    return [float(v) for v in text.strip("[]").split(",")]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class FakePostgres:
    """In-memory stand-in for the PostgreSQL + pgvector database.

    It understands exactly the statements issued by ``KnowledgeBase`` and
    doubles as the connection pool, the connection and the acquire() context.
    """

    def __init__(self, table_exists: bool = False):
        self.table_exists = table_exists
        self.extension_created = False
        self.index_created = False
        self.rows: list[dict] = []
        self.closed = False
        self._next_id = 1

    # pool interface
    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def close(self):
        self.closed = True

    # connection interface
    async def fetchval(self, sql, *args):
        return self.table_exists

    async def execute(self, sql, *args):
        if "CREATE EXTENSION" in sql:
            self.extension_created = True
        elif "CREATE TABLE" in sql:
            self.table_exists = True
        elif "CREATE INDEX" in sql:
            self.index_created = True
        elif "UPDATE knowledge_base" in sql:
            question, answer, embedding, entry_id = args
            for row in self.rows:
                if row["id"] == entry_id:
                    row.update(question=question, answer=answer, embedding=embedding)
        elif "DELETE FROM knowledge_base" in sql:
            self.rows = [row for row in self.rows if row["id"] != args[0]]

    async def fetchrow(self, sql, *args):
        question, answer, embedding = args
        row = {"id": self._next_id, "question": question, "answer": answer, "embedding": embedding}
        self._next_id += 1
        self.rows.append(row)
        return {"id": row["id"]}

    async def fetch(self, sql, *args):
        if "RANDOM()" in sql:
            return [{"question": row["question"]} for row in self.rows[: args[0]]]
        query = _parse_vector(args[0])
        ranked = sorted(
            (
                {**row, "similarity": _cosine(query, _parse_vector(row["embedding"]))}
                for row in self.rows
            ),
            key=lambda row: row["similarity"],
            reverse=True,
        )
        return ranked[: args[1]]


def install_fake_knowledge_backends(database: FakePostgres):
    """Patch asyncpg and the OpenAI embeddings client used by the knowledge base.

    Returns the started patchers; the caller must stop them.
    """
    embeddings = AsyncMock()

    async def create(model, input):  # noqa: A002 - mirrors the OpenAI signature
        return MagicMock(data=[MagicMock(embedding=embed(input))])

    embeddings.embeddings.create = create
    patchers = [
        patch(
            "asterisk.knowledge_base.asyncpg.create_pool",
            new=AsyncMock(return_value=database),
        ),
        patch("asterisk.knowledge_base.AsyncOpenAI", return_value=embeddings),
    ]
    for patcher in patchers:
        patcher.start()
    return patchers
