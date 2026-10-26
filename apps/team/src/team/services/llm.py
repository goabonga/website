# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""LLM client factory for OpenAI and Anthropic providers."""

import json
import logging
from dataclasses import dataclass, field

import anthropic
import openai

from team.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    """Structured response from get_chat_completion."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


async def get_completion(
    provider: str,
    model: str,
    system_prompt: str,
    user_message: str,
) -> str:
    """Get a text completion from an LLM provider.

    Args:
        provider: LLM provider name ("openai" or "anthropic").
        model: Model identifier (e.g. "gpt-4o", "claude-sonnet-4-5-20250929").
        system_prompt: System-level instructions.
        user_message: The user prompt.

    Returns:
        The completion text.

    Raises:
        ValueError: If the provider is not supported or API key is missing.
    """
    if provider == "openai":
        return await _openai_completion(model, system_prompt, user_message)
    elif provider == "anthropic":
        return await _anthropic_completion(model, system_prompt, user_message)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def _openai_completion(model: str, system_prompt: str, user_message: str) -> str:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content or ""
    finally:
        await client.close()


async def _anthropic_completion(model: str, system_prompt: str, user_message: str) -> str:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        block = response.content[0]
        return block.text if hasattr(block, "text") else ""
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Chat completion with tool calling support
# ---------------------------------------------------------------------------


async def get_chat_completion(
    provider: str,
    model: str,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 4096,
) -> ChatResult:
    """Get a chat completion with optional tool calling.

    Args:
        provider: "openai" or "anthropic".
        model: Model identifier.
        system_prompt: System-level instructions.
        messages: Conversation messages.
        tools: Tool definitions in OpenAI format.
        max_tokens: Maximum response tokens.

    Returns:
        ChatResult with content, tool_calls, and stop_reason.
    """
    if provider == "openai":
        return await _openai_chat(model, system_prompt, messages, tools, max_tokens)
    elif provider == "anthropic":
        return await _anthropic_chat(model, system_prompt, messages, tools, max_tokens)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def _openai_chat(
    model: str,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict] | None,
    max_tokens: int,
) -> ChatResult:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        # Build messages with system prompt
        api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            api_messages.append(_normalize_message_for_openai(msg))

        kwargs: dict = {"model": model, "messages": api_messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        result = ChatResult(content=message.content or "")

        if choice.finish_reason == "tool_calls" and message.tool_calls:
            result.stop_reason = "tool_use"
            for tc in message.tool_calls:
                args = tc.function.arguments
                parsed = json.loads(args) if isinstance(args, str) else args
                result.tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=parsed)
                )
        elif choice.finish_reason == "length":
            result.stop_reason = "max_tokens"

        return result
    finally:
        await client.close()


def _normalize_message_for_openai(msg: dict) -> dict:
    """Convert internal message format to OpenAI API format."""
    role = msg.get("role", "user")
    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": msg.get("tool_call_id", ""),
            "content": json.dumps(msg.get("content", {}))
            if isinstance(msg.get("content"), dict)
            else str(msg.get("content", "")),
        }
    if role == "assistant" and "tool_calls" in msg:
        return {
            "role": "assistant",
            "content": msg.get("content") or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"])
                        if isinstance(tc["arguments"], dict)
                        else tc["arguments"],
                    },
                }
                for tc in msg["tool_calls"]
            ],
        }
    return {"role": role, "content": msg.get("content", "")}


async def _anthropic_chat(
    model: str,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict] | None,
    max_tokens: int,
) -> ChatResult:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        # Convert messages to Anthropic format
        api_messages = [_normalize_message_for_anthropic(msg) for msg in messages]

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": api_messages,
        }
        if tools:
            kwargs["tools"] = _convert_tools_to_anthropic(tools)

        response = await client.messages.create(**kwargs)

        result = ChatResult()
        for block in response.content:
            if hasattr(block, "text"):
                result.content += block.text
            elif hasattr(block, "type") and block.type == "tool_use":
                result.tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        if response.stop_reason == "tool_use":
            result.stop_reason = "tool_use"
        elif response.stop_reason == "max_tokens":
            result.stop_reason = "max_tokens"
        else:
            result.stop_reason = "end_turn"

        return result
    finally:
        await client.close()


def _normalize_message_for_anthropic(msg: dict) -> dict:
    """Convert internal message format to Anthropic API format."""
    role = msg.get("role", "user")
    if role == "tool":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": json.dumps(msg.get("content", {}))
                    if isinstance(msg.get("content"), dict)
                    else str(msg.get("content", "")),
                }
            ],
        }
    if role == "assistant" and "tool_calls" in msg:
        content: list[dict] = []
        if msg.get("content"):
            content.append({"type": "text", "text": msg["content"]})
        for tc in msg["tool_calls"]:
            content.append(
                {
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                }
            )
        return {"role": "assistant", "content": content}
    return {"role": role, "content": msg.get("content", "")}


def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool format to Anthropic tool format."""
    result = []
    for tool in tools:
        fn = tool.get("function", tool)
        result.append(
            {
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            }
        )
    return result
