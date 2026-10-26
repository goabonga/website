# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for LLM service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from team.services.llm import ChatResult, get_chat_completion, get_completion


class TestGetCompletion:
    @pytest.mark.asyncio
    async def test_unsupported_provider(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            await get_completion("google", "gemini", "system", "hello")


class TestOpenAICompletion:
    @pytest.mark.asyncio
    async def test_openai_completion(self):
        mock_message = MagicMock()
        mock_message.content = "Hello from GPT"

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as mock_settings,
            patch("team.services.llm.openai.AsyncOpenAI", return_value=mock_client),
        ):
            mock_settings.openai_api_key = "sk-test"

            result = await get_completion("openai", "gpt-4o", "system", "hello")

        assert result == "Hello from GPT"
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_openai_missing_key(self):
        with patch("team.services.llm.settings") as mock_settings:
            mock_settings.openai_api_key = ""

            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                await get_completion("openai", "gpt-4o", "system", "hello")

    @pytest.mark.asyncio
    async def test_openai_none_content(self):
        mock_message = MagicMock()
        mock_message.content = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as mock_settings,
            patch("team.services.llm.openai.AsyncOpenAI", return_value=mock_client),
        ):
            mock_settings.openai_api_key = "sk-test"

            result = await get_completion("openai", "gpt-4o", "system", "hello")

        assert result == ""


class TestAnthropicCompletion:
    @pytest.mark.asyncio
    async def test_anthropic_completion(self):
        mock_block = MagicMock()
        mock_block.text = "Hello from Claude"

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as mock_settings,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            mock_settings.anthropic_api_key = "sk-ant-test"

            result = await get_completion(
                "anthropic", "claude-sonnet-4-5-20250929", "system", "hello"
            )

        assert result == "Hello from Claude"
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_anthropic_missing_key(self):
        with patch("team.services.llm.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""

            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                await get_completion("anthropic", "claude-sonnet-4-5-20250929", "system", "hello")

    @pytest.mark.asyncio
    async def test_anthropic_no_text_attr(self):
        mock_block = MagicMock(spec=[])  # No attributes at all

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as mock_settings,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            mock_settings.anthropic_api_key = "sk-ant-test"

            result = await get_completion(
                "anthropic", "claude-sonnet-4-5-20250929", "system", "hello"
            )

        assert result == ""


# ---------------------------------------------------------------------------
# Chat completion with tool calling
# ---------------------------------------------------------------------------


class TestGetChatCompletion:
    async def test_unsupported_provider(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            await get_chat_completion(
                "google", "gemini", "sys", [{"role": "user", "content": "hi"}]
            )


class TestOpenAIChatCompletion:
    async def test_no_tools(self):
        mock_message = MagicMock()
        mock_message.content = "Hello"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.openai.AsyncOpenAI", return_value=mock_client),
        ):
            s.openai_api_key = "sk-test"
            result = await get_chat_completion(
                "openai", "gpt-4o", "system", [{"role": "user", "content": "hi"}]
            )

        assert isinstance(result, ChatResult)
        assert result.content == "Hello"
        assert result.tool_calls == []
        assert result.stop_reason == "end_turn"

    async def test_with_tool_calls(self):
        mock_tc = MagicMock()
        mock_tc.id = "call_123"
        mock_tc.function.name = "search_memory"
        mock_tc.function.arguments = json.dumps({"query": "test"})

        mock_message = MagicMock()
        mock_message.content = ""
        mock_message.tool_calls = [mock_tc]

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.openai.AsyncOpenAI", return_value=mock_client),
        ):
            s.openai_api_key = "sk-test"
            result = await get_chat_completion(
                "openai",
                "gpt-4o",
                "system",
                [{"role": "user", "content": "search"}],
                tools=[{"type": "function", "function": {"name": "search_memory"}}],
            )

        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "search_memory"
        assert result.tool_calls[0].arguments == {"query": "test"}

    async def test_missing_key(self):
        with patch("team.services.llm.settings") as s:
            s.openai_api_key = ""
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                await get_chat_completion("openai", "gpt-4o", "sys", [])

    async def test_max_tokens_stop(self):
        mock_message = MagicMock()
        mock_message.content = "Truncated"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "length"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.openai.AsyncOpenAI", return_value=mock_client),
        ):
            s.openai_api_key = "sk-test"
            result = await get_chat_completion("openai", "gpt-4o", "sys", [])

        assert result.stop_reason == "max_tokens"


class TestAnthropicChatCompletion:
    async def test_no_tools(self):
        mock_block = MagicMock()
        mock_block.text = "Hello from Claude"
        mock_block.type = "text"

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            s.anthropic_api_key = "sk-ant-test"
            result = await get_chat_completion(
                "anthropic",
                "claude-sonnet-4-5-20250929",
                "system",
                [{"role": "user", "content": "hi"}],
            )

        assert result.content == "Hello from Claude"
        assert result.stop_reason == "end_turn"

    async def test_with_tool_use(self):
        text_block = MagicMock()
        text_block.text = "Let me search."
        text_block.type = "text"

        tool_block = MagicMock(spec=["type", "id", "name", "input"])
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "search_memory"
        tool_block.input = {"query": "test"}

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]
        mock_response.stop_reason = "tool_use"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            s.anthropic_api_key = "sk-ant-test"
            result = await get_chat_completion(
                "anthropic",
                "claude-sonnet-4-5-20250929",
                "system",
                [{"role": "user", "content": "search"}],
                tools=[{"type": "function", "function": {"name": "search_memory"}}],
            )

        assert result.stop_reason == "tool_use"
        assert result.content == "Let me search."
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "toolu_123"
        assert result.tool_calls[0].name == "search_memory"

    async def test_missing_key(self):
        with patch("team.services.llm.settings") as s:
            s.anthropic_api_key = ""
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                await get_chat_completion("anthropic", "claude-sonnet-4-5-20250929", "sys", [])

    async def test_tool_format_conversion(self):
        """Tools should be converted from OpenAI format to Anthropic format."""
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            s.anthropic_api_key = "sk-ant-test"
            await get_chat_completion(
                "anthropic",
                "claude-sonnet-4-5-20250929",
                "system",
                [{"role": "user", "content": "hi"}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "search_memory",
                            "description": "Search memory",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert call_kwargs["tools"][0]["name"] == "search_memory"
        assert "input_schema" in call_kwargs["tools"][0]

    async def test_max_tokens_stop(self):
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "max_tokens"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            s.anthropic_api_key = "sk-ant-test"
            result = await get_chat_completion("anthropic", "claude-sonnet-4-5-20250929", "sys", [])

        assert result.stop_reason == "max_tokens"

    async def test_tool_message_normalization(self):
        """Tool result messages are converted to Anthropic tool_result format."""
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        messages = [
            {"role": "user", "content": "search"},
            {
                "role": "assistant",
                "content": "Let me search.",
                "tool_calls": [
                    {"id": "tc_1", "name": "search_memory", "arguments": {"query": "x"}},
                ],
            },
            {"role": "tool", "tool_call_id": "tc_1", "content": {"results": []}},
        ]

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            s.anthropic_api_key = "sk-ant-test"
            await get_chat_completion(
                "anthropic",
                "claude-sonnet-4-5-20250929",
                "system",
                messages,
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        api_msgs = call_kwargs["messages"]
        # Tool result should be converted to user role with tool_result block
        assert api_msgs[2]["role"] == "user"
        assert api_msgs[2]["content"][0]["type"] == "tool_result"
        # Assistant message should have content blocks with tool_use
        assert api_msgs[1]["role"] == "assistant"
        assert any(b["type"] == "tool_use" for b in api_msgs[1]["content"])

    async def test_unknown_block_type_skipped(self):
        """Blocks without text or tool_use type are silently skipped."""
        # A block with no "text" attr and type != "tool_use"
        unknown_block = MagicMock(spec=["type"])
        unknown_block.type = "thinking"

        mock_response = MagicMock()
        mock_response.content = [unknown_block]
        mock_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            s.anthropic_api_key = "sk-ant-test"
            result = await get_chat_completion(
                "anthropic",
                "claude-sonnet-4-5-20250929",
                "sys",
                [{"role": "user", "content": "hi"}],
            )

        assert result.content == ""
        assert result.stop_reason == "end_turn"

    async def test_assistant_tool_calls_no_content(self):
        """Assistant messages with tool_calls but empty content are normalized."""
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        messages = [
            {"role": "user", "content": "search"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "name": "search_memory", "arguments": {"query": "x"}},
                ],
            },
            {"role": "tool", "tool_call_id": "tc_1", "content": {"results": []}},
        ]

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            s.anthropic_api_key = "sk-ant-test"
            await get_chat_completion(
                "anthropic",
                "claude-sonnet-4-5-20250929",
                "system",
                messages,
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        api_msgs = call_kwargs["messages"]
        # Assistant content should only have tool_use blocks (no text block)
        assistant_content = api_msgs[1]["content"]
        assert all(b["type"] == "tool_use" for b in assistant_content)


class TestOpenAIMessageNormalization:
    async def test_tool_message_normalization(self):
        """Tool result messages are converted to OpenAI tool format."""
        mock_message = MagicMock()
        mock_message.content = "Done"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        messages = [
            {"role": "user", "content": "search"},
            {
                "role": "assistant",
                "content": "Searching.",
                "tool_calls": [
                    {"id": "call_1", "name": "search_memory", "arguments": {"query": "x"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": {"results": []}},
        ]

        with (
            patch("team.services.llm.settings") as s,
            patch("team.services.llm.openai.AsyncOpenAI", return_value=mock_client),
        ):
            s.openai_api_key = "sk-test"
            await get_chat_completion(
                "openai",
                "gpt-4o",
                "system",
                messages,
            )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        api_msgs = call_kwargs["messages"]
        # Tool result should keep role="tool" with string content
        assert api_msgs[-1]["role"] == "tool"
        assert api_msgs[-1]["tool_call_id"] == "call_1"
        # Assistant message should have tool_calls with function format
        assert api_msgs[-2]["role"] == "assistant"
        assert api_msgs[-2]["tool_calls"][0]["type"] == "function"
