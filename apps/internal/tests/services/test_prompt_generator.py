# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for prompt generator service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_openai():
    with patch("internal.services.prompt_generator.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        MockOpenAI.return_value = mock_client
        yield mock_client


@pytest.fixture
def service(mock_openai):
    with patch("internal.services.prompt_generator.settings") as s:
        s.openai_api_key = "sk-test"
        from internal.services.prompt_generator import PromptGeneratorService

        svc = PromptGeneratorService()
        svc.client = mock_openai
        yield svc


def _make_completion(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestGeneratePrompt:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_openai):
        result_data = {
            "name": "Customer Support",
            "slug": "customer-support",
            "description": "A customer support assistant",
            "content": "You are a helpful customer support agent.",
        }
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(result_data))

        result = await service.generate_prompt("A customer support bot")
        assert result["name"] == "Customer Support"
        assert result["slug"] == "customer-support"
        assert result["content"] == "You are a helpful customer support agent."

    @pytest.mark.asyncio
    async def test_missing_fields_returns_empty(self, service, mock_openai):
        incomplete = {"name": "Test", "slug": "test"}  # missing description and content
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(incomplete))

        result = await service.generate_prompt("A test prompt")
        assert result == {}

    @pytest.mark.asyncio
    async def test_json_decode_error(self, service, mock_openai):
        mock_openai.chat.completions.create.return_value = _make_completion("not json")

        result = await service.generate_prompt("A test prompt")
        assert result == {}

    @pytest.mark.asyncio
    async def test_api_error_raises(self, service, mock_openai):
        mock_openai.chat.completions.create.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await service.generate_prompt("A test prompt")

    @pytest.mark.asyncio
    async def test_slug_is_sanitized(self, service, mock_openai):
        result_data = {
            "name": "Test",
            "slug": "Test Slug With CAPS!",
            "description": "desc",
            "content": "content",
        }
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(result_data))

        result = await service.generate_prompt("test")
        assert result["slug"] == "test-slug-with-caps"

    @pytest.mark.asyncio
    async def test_focus_areas_and_constraints(self, service, mock_openai):
        result_data = {
            "name": "Test",
            "slug": "test",
            "description": "desc",
            "content": "content",
        }
        mock_openai.chat.completions.create.return_value = _make_completion(json.dumps(result_data))

        await service.generate_prompt(
            "test",
            focus_areas="security",
            constraints="no jargon",
        )
        call_args = mock_openai.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "security" in user_msg
        assert "no jargon" in user_msg


class TestSanitizeSlug:
    def _sanitize(self, slug):
        with patch("internal.services.prompt_generator.settings") as s:
            s.openai_api_key = "sk-test"
            from internal.services.prompt_generator import PromptGeneratorService

            return PromptGeneratorService()._sanitize_slug(slug)

    def test_lowercase(self):
        assert self._sanitize("Hello-World") == "hello-world"

    def test_spaces_to_hyphens(self):
        assert self._sanitize("hello world") == "hello-world"

    def test_underscores_to_hyphens(self):
        assert self._sanitize("hello_world") == "hello-world"

    def test_special_chars_removed(self):
        assert self._sanitize("hello!@#world") == "helloworld"

    def test_multiple_hyphens_collapsed(self):
        assert self._sanitize("hello---world") == "hello-world"

    def test_leading_trailing_hyphens_stripped(self):
        assert self._sanitize("-hello-world-") == "hello-world"

    def test_empty_returns_default(self):
        assert self._sanitize("") == "generated-prompt"

    def test_only_special_chars(self):
        assert self._sanitize("!@#$%") == "generated-prompt"
