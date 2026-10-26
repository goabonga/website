# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Async OpenAI client wrapper with retry logic and streaming support."""

import json
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk, ChatCompletionMessageParam

from backend.config import settings
from backend.logging import get_logger

logger = get_logger(__name__)

# Model families that reject max_tokens and a custom temperature
_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _generation_params(model: str, temperature: float, max_tokens: int) -> dict[str, Any]:
    """Build the token limit and sampling kwargs accepted by the model.

    Recent models require max_completion_tokens instead of max_tokens, and the
    reasoning families only support the default temperature.
    """
    params: dict[str, Any] = {"max_completion_tokens": max_tokens}
    if not model.startswith(_REASONING_MODEL_PREFIXES):
        params["temperature"] = temperature
    return params


class OpenAIClient:
    """Async OpenAI client with streaming and tool calling support."""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a chat completion request and return the response.

        Args:
            messages: Chat messages
            tools: Optional list of tools in OpenAI format
            tool_choice: "auto", "required", or "none" - controls tool usage
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response (sent as max_completion_tokens)
        """
        logger.info(
            "OpenAI chat request: model=%s, messages=%d, tools=%d",
            self.model,
            len(messages),
            len(tools) if tools else 0,
        )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            **_generation_params(self.model, temperature, max_tokens),
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("OpenAI API error: %s", str(e))
            raise

        message = response.choices[0].message

        result: dict[str, Any] = {
            "content": message.content,
            "role": message.role,
            "tool_calls": None,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in message.tool_calls
            ]
            logger.info("OpenAI returned %d tool calls", len(message.tool_calls))

        logger.info(
            "OpenAI response: %d prompt tokens, %d completion tokens",
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
        )
        return result

    async def stream(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream chat completion tokens."""
        logger.info("OpenAI stream request: model=%s, messages=%d", self.model, len(messages))

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **_generation_params(self.model, temperature, max_tokens),
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as e:
            logger.error("OpenAI API stream error: %s", str(e))
            raise

        token_count = 0
        chunk: ChatCompletionChunk
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token_count += 1
                yield {
                    "type": "token",
                    "content": chunk.choices[0].delta.content,
                }
            if chunk.usage:
                logger.info(
                    "OpenAI stream completed: %d tokens streamed, %d prompt, %d completion",
                    token_count,
                    chunk.usage.prompt_tokens,
                    chunk.usage.completion_tokens,
                )
                yield {
                    "type": "usage",
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                }

    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> list[float]:
        """Generate embedding for text."""
        logger.info("Generating embedding: model=%s, text_length=%d", model, len(text))
        try:
            response = await self.client.embeddings.create(
                model=model,
                input=text,
            )
            logger.info("Embedding generated: %d dimensions", len(response.data[0].embedding))
            return response.data[0].embedding
        except Exception as e:
            logger.error("OpenAI embedding error: %s", str(e))
            raise
