# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for sync knowledge generator service."""

import json
from unittest.mock import MagicMock, patch

import pytest
from internal.services.knowledge_generator_sync import SyncKnowledgeGeneratorService


def _make_completion(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestSyncKnowledgeGeneratorService:
    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_generate_entries_success(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        entries = [
            {"question": "What is X?", "answer": "X is Y.", "metadata": {}},
            {"question": "How does Z?", "answer": "Z works by...", "metadata": {}},
        ]
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"entries": entries})
        )

        service = SyncKnowledgeGeneratorService()
        result = service.generate_entries("Some long source text", num_entries=2)

        assert len(result) == 2
        assert result[0]["question"] == "What is X?"

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_generate_entries_with_context(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"entries": [{"question": "Q?", "answer": "A."}]})
        )

        service = SyncKnowledgeGeneratorService()
        result = service.generate_entries("Source text", num_entries=1, context="Focus on tech")

        assert len(result) == 1
        call_args = mock_client.chat.completions.create.call_args
        user_content = call_args[1]["messages"][1]["content"]
        assert "Focus on tech" in user_content

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_response_as_list(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        entries = [{"question": "Q?", "answer": "A."}]
        mock_client.chat.completions.create.return_value = _make_completion(json.dumps(entries))

        service = SyncKnowledgeGeneratorService()
        result = service.generate_entries("Source text", num_entries=1)

        assert len(result) == 1

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_response_with_unknown_key(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"data": [{"question": "Q?", "answer": "A."}]})
        )

        service = SyncKnowledgeGeneratorService()
        result = service.generate_entries("Source text")

        assert len(result) == 1

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_response_no_list_found(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"status": "ok"})
        )

        service = SyncKnowledgeGeneratorService()
        result = service.generate_entries("Source text")

        assert result == []

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_json_decode_error(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion("not valid json")

        service = SyncKnowledgeGeneratorService()
        result = service.generate_entries("Source text")

        assert result == []

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_api_error_raises(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.side_effect = RuntimeError("API down")

        service = SyncKnowledgeGeneratorService()
        with pytest.raises(RuntimeError, match="API down"):
            service.generate_entries("Source text")

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_empty_content(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion("")

        service = SyncKnowledgeGeneratorService()
        result = service.generate_entries("Source text")

        assert result == []

    @patch("internal.services.knowledge_generator_sync.settings")
    @patch("internal.services.knowledge_generator_sync.OpenAI")
    def test_num_entries_clamped(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"entries": []})
        )

        service = SyncKnowledgeGeneratorService()
        service.generate_entries("Source text", num_entries=100)

        call_args = mock_client.chat.completions.create.call_args
        user_content = call_args[1]["messages"][1]["content"]
        assert "50" in user_content
