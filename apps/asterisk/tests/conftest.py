# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all app-relevant env vars so Config picks up only test-set values."""
    env_vars = [
        "AUDIOSOCKET_HOST",
        "AUDIOSOCKET_PORT",
        "LOG_LEVEL",
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
