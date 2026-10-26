# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for chat SSE streaming utilities."""

import json

from backend.chat.stream import format_sse_event, stream_chat_response

# ---------------------------------------------------------------------------
# format_sse_event
# ---------------------------------------------------------------------------


async def test_format_sse_event():
    """format_sse_event formats an SSE event correctly."""
    result = await format_sse_event("token", {"content": "hello"})

    assert result == f"event: token\ndata: {json.dumps({'content': 'hello'})}\n\n"
    assert result.startswith("event: token\n")
    assert "data: " in result
    assert result.endswith("\n\n")


# ---------------------------------------------------------------------------
# Helper: create an async generator from a list of events
# ---------------------------------------------------------------------------


async def _make_generator(events):
    """Create an async generator that yields the given events."""
    for event in events:
        yield event


async def _make_failing_generator(events, error):
    """Create an async generator that yields events then raises an error."""
    for event in events:
        yield event
    raise error


# ---------------------------------------------------------------------------
# stream_chat_response - intent event
# ---------------------------------------------------------------------------


async def test_stream_chat_response_intent():
    """stream_chat_response handles intent event."""
    gen = _make_generator([{"type": "intent", "intent": "rag_search"}])

    results = []
    async for chunk in stream_chat_response(gen):
        results.append(chunk)

    assert len(results) == 1
    parsed = json.loads(results[0].split("data: ")[1].strip())
    assert parsed["intent"] == "rag_search"
    assert results[0].startswith("event: intent\n")


# ---------------------------------------------------------------------------
# stream_chat_response - tools event
# ---------------------------------------------------------------------------


async def test_stream_chat_response_tools():
    """stream_chat_response handles tools event."""
    tool_results = [{"tool": "search", "success": True, "data": "found", "error": None}]
    gen = _make_generator([{"type": "tools", "results": tool_results}])

    results = []
    async for chunk in stream_chat_response(gen):
        results.append(chunk)

    assert len(results) == 1
    parsed = json.loads(results[0].split("data: ")[1].strip())
    assert parsed["results"] == tool_results
    assert results[0].startswith("event: tools\n")


# ---------------------------------------------------------------------------
# stream_chat_response - rag event
# ---------------------------------------------------------------------------


async def test_stream_chat_response_rag():
    """stream_chat_response handles rag event."""
    gen = _make_generator([{"type": "rag", "count": 3}])

    results = []
    async for chunk in stream_chat_response(gen):
        results.append(chunk)

    assert len(results) == 1
    parsed = json.loads(results[0].split("data: ")[1].strip())
    assert parsed["count"] == 3
    assert results[0].startswith("event: rag\n")


# ---------------------------------------------------------------------------
# stream_chat_response - token event
# ---------------------------------------------------------------------------


async def test_stream_chat_response_token():
    """stream_chat_response handles token event."""
    gen = _make_generator([{"type": "token", "content": "Hello"}])

    results = []
    async for chunk in stream_chat_response(gen):
        results.append(chunk)

    assert len(results) == 1
    parsed = json.loads(results[0].split("data: ")[1].strip())
    assert parsed["content"] == "Hello"
    assert results[0].startswith("event: token\n")


# ---------------------------------------------------------------------------
# stream_chat_response - done event
# ---------------------------------------------------------------------------


async def test_stream_chat_response_done():
    """stream_chat_response handles done event."""
    gen = _make_generator(
        [
            {
                "type": "done",
                "conversation_id": "abc-123",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        ]
    )

    results = []
    async for chunk in stream_chat_response(gen):
        results.append(chunk)

    assert len(results) == 1
    parsed = json.loads(results[0].split("data: ")[1].strip())
    assert parsed["conversation_id"] == "abc-123"
    assert parsed["usage"]["prompt_tokens"] == 10
    assert parsed["usage"]["completion_tokens"] == 5
    assert results[0].startswith("event: done\n")


# ---------------------------------------------------------------------------
# stream_chat_response - error from generator exception
# ---------------------------------------------------------------------------


async def test_stream_chat_response_error():
    """stream_chat_response handles error from generator exception."""
    gen = _make_failing_generator(
        [{"type": "token", "content": "partial"}],
        RuntimeError("something went wrong"),
    )

    results = []
    async for chunk in stream_chat_response(gen):
        results.append(chunk)

    # Should have the token event and then the error event
    assert len(results) == 2

    # First is the token
    assert results[0].startswith("event: token\n")

    # Second is the error
    assert results[1].startswith("event: error\n")
    parsed = json.loads(results[1].split("data: ")[1].strip())
    assert parsed["message"] == "something went wrong"


# ---------------------------------------------------------------------------
# stream_chat_response - history event (unhandled type, not emitted)
# ---------------------------------------------------------------------------


async def test_stream_chat_response_history_event_not_emitted():
    """stream_chat_response does not emit SSE for unhandled event types like 'history'."""
    gen = _make_generator(
        [
            {"type": "history", "messages": [{"role": "user", "content": "hi"}]},
            {"type": "token", "content": "Hello"},
        ]
    )

    results = []
    async for chunk in stream_chat_response(gen):
        results.append(chunk)

    # Only the token event should be emitted; history is not handled
    assert len(results) == 1
    assert results[0].startswith("event: token\n")
    parsed = json.loads(results[0].split("data: ")[1].strip())
    assert parsed["content"] == "Hello"
