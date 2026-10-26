# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SSE streaming utilities for chat responses."""

import json
from collections.abc import AsyncGenerator
from typing import Any


async def format_sse_event(
    event: str,
    data: dict[str, Any],
) -> str:
    """Format a Server-Sent Event message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_chat_response(
    generator: AsyncGenerator[dict[str, Any], None],
) -> AsyncGenerator[str, None]:
    """
    Convert chat orchestrator stream to SSE format.

    Event types:
    - intent: Intent classification result
    - tools: Tool execution results
    - rag: RAG search results count
    - token: Individual token from LLM
    - done: Stream complete with usage stats
    - error: Error occurred
    """
    try:
        async for chunk in generator:
            chunk_type = chunk.get("type", "")

            if chunk_type == "intent":
                yield await format_sse_event(
                    "intent",
                    {
                        "intent": chunk["intent"],
                    },
                )

            elif chunk_type == "tools":
                yield await format_sse_event(
                    "tools",
                    {
                        "results": chunk["results"],
                    },
                )

            elif chunk_type == "rag":
                yield await format_sse_event(
                    "rag",
                    {
                        "count": chunk["count"],
                    },
                )

            elif chunk_type == "token":
                yield await format_sse_event(
                    "token",
                    {
                        "content": chunk["content"],
                    },
                )

            elif chunk_type == "done":
                yield await format_sse_event(
                    "done",
                    {
                        "conversation_id": chunk.get("conversation_id"),
                        "usage": chunk.get("usage", {}),
                    },
                )

    except Exception as e:
        yield await format_sse_event(
            "error",
            {
                "message": str(e),
            },
        )
