# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.llm.client.OpenAIClient."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.llm.client import OpenAIClient

# ---------------------------------------------------------------------------
# Helpers to build mock OpenAI responses
# ---------------------------------------------------------------------------


def _make_chat_response(
    content="Hello!", role="assistant", tool_calls=None, prompt_tokens=10, completion_tokens=5
):
    """Build a MagicMock that mimics an OpenAI ChatCompletion response."""
    message = MagicMock()
    message.content = content
    message.role = role
    message.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def _make_tool_call(tc_id="call_abc123", name="search_knowledge", arguments=None):
    """Build a MagicMock that mimics an OpenAI tool call object."""
    if arguments is None:
        arguments = {"query": "test"}

    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_embedding_response(embedding=None):
    """Build a MagicMock that mimics an OpenAI embeddings response."""
    if embedding is None:
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

    data_item = MagicMock()
    data_item.embedding = embedding

    response = MagicMock()
    response.data = [data_item]
    return response


class _AsyncChunkIterator:
    """Async iterator that yields pre-built stream chunks."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def _make_stream_chunk(content=None, usage=None):
    """Build a MagicMock that mimics a ChatCompletionChunk."""
    chunk = MagicMock()

    if content is not None:
        delta = MagicMock()
        delta.content = content
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]
    else:
        chunk.choices = []

    if usage is not None:
        usage_obj = MagicMock()
        usage_obj.prompt_tokens = usage["prompt_tokens"]
        usage_obj.completion_tokens = usage["completion_tokens"]
        chunk.usage = usage_obj
    else:
        chunk.usage = None

    return chunk


# ---------------------------------------------------------------------------
# Fixture: patched OpenAIClient
# ---------------------------------------------------------------------------


@pytest.fixture
def openai_client():
    """Create an OpenAIClient with mocked internals."""
    with (
        patch("backend.llm.client.AsyncOpenAI"),
        patch("backend.llm.client.settings") as mock_settings,
    ):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.openai_model = "gpt-4o-mini"
        client = OpenAIClient()
        # Replace the inner AsyncOpenAI instance with an AsyncMock
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock()
        client.client.embeddings = MagicMock()
        client.client.embeddings.create = AsyncMock()
        yield client


# ===========================================================================
# Tests for chat()
# ===========================================================================


class TestOpenAIClientChat:
    """Tests for OpenAIClient.chat()."""

    async def test_chat_returns_content_role_and_usage(self, openai_client):
        """chat() returns content, role, and usage from the API response."""
        mock_response = _make_chat_response(
            content="Hello from GPT!",
            role="assistant",
            prompt_tokens=15,
            completion_tokens=8,
        )
        openai_client.client.chat.completions.create.return_value = mock_response

        result = await openai_client.chat(
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result["content"] == "Hello from GPT!"
        assert result["role"] == "assistant"
        assert result["tool_calls"] is None
        assert result["usage"]["prompt_tokens"] == 15
        assert result["usage"]["completion_tokens"] == 8

    async def test_chat_with_tool_calls_parses_function(self, openai_client):
        """chat() correctly parses tool_calls with function name and JSON arguments."""
        tc = _make_tool_call(
            tc_id="call_xyz",
            name="search_knowledge",
            arguments={"query": "Python async"},
        )
        mock_response = _make_chat_response(
            content=None,
            tool_calls=[tc],
        )
        openai_client.client.chat.completions.create.return_value = mock_response

        result = await openai_client.chat(
            messages=[{"role": "user", "content": "Search for Python async"}],
        )

        assert result["tool_calls"] is not None
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["id"] == "call_xyz"
        assert result["tool_calls"][0]["name"] == "search_knowledge"
        assert result["tool_calls"][0]["arguments"] == {"query": "Python async"}

    async def test_chat_with_tools_passes_tools_and_tool_choice(self, openai_client):
        """chat() passes tools and tool_choice in kwargs when provided."""
        mock_response = _make_chat_response()
        openai_client.client.chat.completions.create.return_value = mock_response

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "description": "Search knowledge base",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        await openai_client.chat(
            messages=[{"role": "user", "content": "test"}],
            tools=tools,
            tool_choice="required",
        )

        call_kwargs = openai_client.client.chat.completions.create.call_args
        assert call_kwargs.kwargs["tools"] == tools
        assert call_kwargs.kwargs["tool_choice"] == "required"

    async def test_chat_without_tools_omits_tools_kwargs(self, openai_client):
        """chat() does not pass tools/tool_choice when tools is None."""
        mock_response = _make_chat_response()
        openai_client.client.chat.completions.create.return_value = mock_response

        await openai_client.chat(
            messages=[{"role": "user", "content": "test"}],
        )

        call_kwargs = openai_client.client.chat.completions.create.call_args.kwargs
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    async def test_chat_sends_max_completion_tokens_and_temperature(self, openai_client):
        """chat() sends max_completion_tokens (not max_tokens) for standard models."""
        openai_client.client.chat.completions.create.return_value = _make_chat_response()

        await openai_client.chat(
            messages=[{"role": "user", "content": "test"}],
            temperature=0.2,
            max_tokens=123,
        )

        kwargs = openai_client.client.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 123
        assert "max_tokens" not in kwargs
        assert kwargs["temperature"] == 0.2

    async def test_chat_omits_temperature_for_reasoning_models(self, openai_client):
        """chat() leaves temperature out for models that only support the default."""
        openai_client.model = "gpt-5.2"
        openai_client.client.chat.completions.create.return_value = _make_chat_response()

        await openai_client.chat(messages=[{"role": "user", "content": "test"}])

        kwargs = openai_client.client.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 4096
        assert "max_tokens" not in kwargs
        assert "temperature" not in kwargs

    async def test_chat_api_error_raises_exception(self, openai_client):
        """chat() re-raises exceptions from the OpenAI API."""
        openai_client.client.chat.completions.create.side_effect = Exception(
            "API rate limit exceeded"
        )

        with pytest.raises(Exception, match="API rate limit exceeded"):
            await openai_client.chat(
                messages=[{"role": "user", "content": "test"}],
            )


# ===========================================================================
# Tests for stream()
# ===========================================================================


class TestOpenAIClientStream:
    """Tests for OpenAIClient.stream()."""

    async def test_stream_yields_tokens_then_usage(self, openai_client):
        """stream() yields token events followed by a usage event."""
        chunks = [
            _make_stream_chunk(content="Hello"),
            _make_stream_chunk(content=" world"),
            _make_stream_chunk(
                content=None,
                usage={"prompt_tokens": 10, "completion_tokens": 2},
            ),
        ]
        openai_client.client.chat.completions.create.return_value = _AsyncChunkIterator(chunks)

        results = []
        async for event in openai_client.stream(
            messages=[{"role": "user", "content": "Hi"}],
        ):
            results.append(event)

        assert len(results) == 3
        assert results[0] == {"type": "token", "content": "Hello"}
        assert results[1] == {"type": "token", "content": " world"}
        assert results[2] == {
            "type": "usage",
            "prompt_tokens": 10,
            "completion_tokens": 2,
        }

    async def test_stream_uses_max_completion_tokens(self, openai_client):
        """stream() sends max_completion_tokens (not max_tokens)."""
        openai_client.model = "gpt-5.2"
        openai_client.client.chat.completions.create.return_value = _AsyncChunkIterator([])

        async for _ in openai_client.stream(messages=[{"role": "user", "content": "Hi"}]):
            pass

        kwargs = openai_client.client.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 4096
        assert "max_tokens" not in kwargs
        assert "temperature" not in kwargs

    async def test_stream_skips_empty_content_chunks(self, openai_client):
        """stream() skips chunks with no content in delta."""
        chunks = [
            _make_stream_chunk(content=None),  # empty delta, no usage
            _make_stream_chunk(content="data"),
            _make_stream_chunk(
                content=None,
                usage={"prompt_tokens": 5, "completion_tokens": 1},
            ),
        ]
        openai_client.client.chat.completions.create.return_value = _AsyncChunkIterator(chunks)

        results = []
        async for event in openai_client.stream(
            messages=[{"role": "user", "content": "Hi"}],
        ):
            results.append(event)

        assert len(results) == 2
        assert results[0] == {"type": "token", "content": "data"}
        assert results[1]["type"] == "usage"

    async def test_stream_api_error_raises_exception(self, openai_client):
        """stream() re-raises exceptions from the OpenAI API."""
        openai_client.client.chat.completions.create.side_effect = Exception(
            "Stream connection failed"
        )

        with pytest.raises(Exception, match="Stream connection failed"):
            async for _ in openai_client.stream(
                messages=[{"role": "user", "content": "test"}],
            ):
                pass  # pragma: no cover


# ===========================================================================
# Tests for get_embedding()
# ===========================================================================


class TestOpenAIClientGetEmbedding:
    """Tests for OpenAIClient.get_embedding()."""

    async def test_get_embedding_returns_list(self, openai_client):
        """get_embedding() returns the embedding vector as a list of floats."""
        expected = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_response = _make_embedding_response(embedding=expected)
        openai_client.client.embeddings.create.return_value = mock_response

        result = await openai_client.get_embedding("test text")

        assert result == expected
        openai_client.client.embeddings.create.assert_awaited_once_with(
            model="text-embedding-3-small",
            input="test text",
        )

    async def test_get_embedding_custom_model(self, openai_client):
        """get_embedding() uses the specified model parameter."""
        mock_response = _make_embedding_response(embedding=[0.9, 0.8])
        openai_client.client.embeddings.create.return_value = mock_response

        result = await openai_client.get_embedding("test", model="text-embedding-ada-002")

        assert result == [0.9, 0.8]
        openai_client.client.embeddings.create.assert_awaited_once_with(
            model="text-embedding-ada-002",
            input="test",
        )

    async def test_get_embedding_api_error_raises_exception(self, openai_client):
        """get_embedding() re-raises exceptions from the OpenAI API."""
        openai_client.client.embeddings.create.side_effect = Exception(
            "Embedding service unavailable"
        )

        with pytest.raises(Exception, match="Embedding service unavailable"):
            await openai_client.get_embedding("test")
