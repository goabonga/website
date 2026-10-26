# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all app-relevant env vars so Config picks up only test-set values."""
    env_vars = [
        "AUDIOSOCKET_HOST",
        "AUDIOSOCKET_PORT",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_VOICE",
        "OPENAI_SYSTEM_PROMPT",
        "DATABASE_URL",
        "RAG_ENABLED",
        "RAG_EMBEDDING_MODEL",
        "RAG_SIMILARITY_THRESHOLD",
        "RAG_MAX_RESULTS",
        "LOG_LEVEL",
        "CREDENTIALS_DIRECTORY",
        "GREETING_MESSAGE",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)


# --- AsyncIO StreamReader/Writer mocks (fake Asterisk side of AudioSocket) ---


@pytest.fixture
def mock_stream_reader():
    """Return an AsyncMock of asyncio.StreamReader."""
    return AsyncMock(spec=asyncio.StreamReader)


@pytest.fixture
def mock_stream_writer():
    """Return a MagicMock of asyncio.StreamWriter (write is sync, drain is async)."""
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 9999))
    return writer


@pytest.fixture
def audiosocket_session(mock_stream_reader, mock_stream_writer):
    """Return a fresh AudioSocketSession with mocked reader/writer."""
    from asterisk.audiosocket import AudioSocketSession

    return AudioSocketSession(mock_stream_reader, mock_stream_writer)


@pytest.fixture
def silence_320():
    """320 bytes of silence (zero-valued PCM), one 20 ms AudioSocket frame."""
    return b"\x00" * 320


@pytest.fixture
def tone_8k_samples():
    """Generate a 440Hz tone at 8kHz, 20ms (160 samples = 320 bytes)."""
    t = np.arange(160) / 8000
    samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype("<i2")
    return samples.tobytes()


@pytest.fixture
def tone_24k_samples():
    """Generate a 440Hz tone at 24kHz, 20ms (480 samples = 960 bytes)."""
    t = np.arange(480) / 24000
    samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype("<i2")
    return samples.tobytes()


# --- WebSocket mock (fake OpenAI side) ---


@pytest.fixture
def mock_websocket():
    """Return an AsyncMock that behaves like a websockets ClientConnection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    ws.recv = AsyncMock()
    return ws


@pytest.fixture
def mock_credentials_dir(tmp_path, monkeypatch):
    """Set up a temp CREDENTIALS_DIRECTORY with a fake OPENAI_API_KEY file."""
    cred_file = tmp_path / "OPENAI_API_KEY"
    cred_file.write_text("sk-test-from-creds\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    return tmp_path


# --- asyncpg pool mock (fake PostgreSQL) ---


@pytest.fixture
def mock_asyncpg_pool():
    """Return a mock asyncpg pool with acquire() context manager."""
    pool = MagicMock()
    conn = AsyncMock()
    # Default: table does not exist, so _ensure_schema runs DDL
    conn.fetchval = AsyncMock(return_value=False)

    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=conn)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx_manager
    pool.close = AsyncMock()

    return pool, conn


# --- OpenAI embeddings mock (fake OpenAI embeddings API) ---


@pytest.fixture
def mock_openai_embeddings():
    """Return a mock AsyncOpenAI with embeddings.create returning a vector."""
    client = AsyncMock()
    embedding_response = MagicMock()
    embedding_data = MagicMock()
    embedding_data.embedding = [0.1] * 1536
    embedding_response.data = [embedding_data]
    client.embeddings.create = AsyncMock(return_value=embedding_response)
    return client


# --- Knowledge base singleton reset ---


@pytest.fixture(autouse=True)
def reset_knowledge_base_singleton():
    """Reset the knowledge base module-level singleton between tests."""
    import asterisk.knowledge_base as kb_module

    kb_module._knowledge_base = None
    yield
    kb_module._knowledge_base = None
