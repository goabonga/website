# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tool service with registry, execution, and result formatting."""

import logging
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)


class ToolService:
    """Register, resolve, and execute tools."""

    _registry: ClassVar[dict[str, tuple[Callable[..., Coroutine[Any, Any, dict]], dict]]] = {}

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def register(cls, name: str, definition: dict):
        """Decorator to register a built-in tool handler."""

        def decorator(func: Callable[..., Coroutine[Any, Any, dict]]):
            cls._registry[name] = (func, definition)
            return func

        return decorator

    def get_tool_definitions(self, tool_names: list[str]) -> list[dict]:
        """Return OpenAI-format tool definitions for the given names."""
        definitions = []
        for name in tool_names:
            entry = self._registry.get(name)
            if not entry:
                logger.warning(f"Unknown tool: {name}")
                continue
            _, defn = entry
            definitions.append(
                {
                    "type": "function",
                    "function": defn,
                }
            )
        return definitions

    async def execute_tool(self, tool_name: str, params: dict, context: dict) -> dict:
        """Execute a tool by name."""
        entry = self._registry.get(tool_name)
        if not entry:
            return {"error": f"Unknown tool: {tool_name}"}

        handler, _ = entry
        context["tool_service"] = self
        logger.info(f"Executing tool: {tool_name}")
        return await handler(params, context)

    async def format_tool_result(self, tool_call_id: str, result: dict) -> dict:
        """Format a tool execution result as a message for the LLM."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create an HTTP client for tool use."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
