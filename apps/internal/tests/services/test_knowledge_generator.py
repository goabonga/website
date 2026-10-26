# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge generator service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_openai():
    with patch("internal.services.knowledge_generator.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        MockOpenAI.return_value = mock_client
        yield mock_client


@pytest.fixture
def service(mock_openai):
    with patch("internal.services.knowledge_generator.settings") as s:
        s.openai_api_key = "sk-test"
        from internal.services.knowledge_generator import KnowledgeGeneratorService

        svc = KnowledgeGeneratorService()
        svc.client = mock_openai
        yield svc


def _make_completion(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    # For the hasattr check in the source
    del response.content
    return response


class TestGenerateEntries:
    @pytest.mark.asyncio
    async def test_array_response(self, service, mock_openai):
        entries = [
            {"question": "What is X?", "answer": "X is Y", "metadata": {"tags": ["test"]}},
        ]
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(entries))

        result = await service.generate_entries("Source text about X", num_entries=1)
        assert len(result) == 1
        assert result[0]["question"] == "What is X?"

    @pytest.mark.asyncio
    async def test_object_with_entries_key(self, service, mock_openai):
        data = {
            "entries": [
                {"question": "Q1?", "answer": "A1", "metadata": {}},
                {"question": "Q2?", "answer": "A2", "metadata": {}},
            ]
        }
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(data))

        result = await service.generate_entries("Source text", num_entries=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_object_with_other_array_key(self, service, mock_openai):
        data = {
            "pairs": [
                {"question": "Q?", "answer": "A", "metadata": {}},
            ]
        }
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(data))

        result = await service.generate_entries("Source text", num_entries=1)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_unexpected_format_returns_empty(self, service, mock_openai):
        mock_openai.chat.completions.create.return_value = _make_completion(
            json.dumps({"key": "value"})
        )

        result = await service.generate_entries("Source text", num_entries=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_json_decode_error_returns_empty(self, service, mock_openai):
        mock_openai.chat.completions.create.return_value = _make_completion("not json")

        result = await service.generate_entries("Source text")
        assert result == []

    @pytest.mark.asyncio
    async def test_api_error_raises(self, service, mock_openai):
        mock_openai.chat.completions.create.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await service.generate_entries("Source text")

    @pytest.mark.asyncio
    async def test_num_entries_clamped(self, service, mock_openai):
        entries = [{"question": "Q?", "answer": "A", "metadata": {}}]
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(entries))

        # num_entries should be clamped to 1-20
        await service.generate_entries("text", num_entries=0)
        call_args = mock_openai.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "exactly 1" in user_msg

    @pytest.mark.asyncio
    async def test_with_context(self, service, mock_openai):
        entries = [{"question": "Q?", "answer": "A", "metadata": {}}]
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(entries))

        await service.generate_entries("text", context="Focus on security")
        call_args = mock_openai.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "Focus on security" in user_msg
