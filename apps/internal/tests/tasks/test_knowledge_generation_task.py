# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Celery knowledge generation task."""

from unittest.mock import MagicMock, patch

import pytest


class TestGenerateKnowledgeEntriesTask:
    @pytest.fixture(autouse=True)
    def mock_openai_clients(self):
        """The sync services build an OpenAI client on construction, which needs a key."""
        with (
            patch("internal.services.knowledge_generator_sync.OpenAI"),
            patch("internal.services.embeddings_sync.OpenAI"),
        ):
            yield

    @pytest.fixture(autouse=True)
    def mock_update_state(self):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        with patch.object(generate_knowledge_entries, "update_state"):
            yield

    @patch("internal.tasks.knowledge_generation.get_sync_db_session")
    @patch("internal.services.embeddings_sync.SyncEmbeddingService.generate")
    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_success(self, mock_gen_entries, mock_emb_generate, mock_get_db):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_ns = MagicMock()
        mock_ns.slug = "general"
        mock_db.get.return_value = mock_ns

        mock_gen_entries.return_value = [
            {"question": "Q1?", "answer": "A1.", "metadata": {"tag": "test"}},
            {"question": "Q2?", "answer": "A2.", "metadata": {}},
        ]
        mock_emb_generate.return_value = [0.1, 0.2]

        with patch("internal.tasks.knowledge_generation.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.validation_enabled = False
            result = generate_knowledge_entries.run("source text", 5, None, 1)

        assert result["created_count"] == 2
        assert len(result["entry_ids"]) == 2
        assert result["namespace_slug"] == "general"
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()

    @patch("internal.tasks.knowledge_generation.get_sync_db_session")
    @patch("internal.services.embeddings_sync.SyncEmbeddingService.generate")
    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_success_with_validation(self, mock_gen_entries, mock_emb_generate, mock_get_db):
        from internal.tasks.knowledge_generation import generate_knowledge_entries
        from internal.tasks.knowledge_validation import validate_knowledge_entry

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_ns = MagicMock()
        mock_ns.slug = "general"
        mock_db.get.return_value = mock_ns

        mock_gen_entries.return_value = [
            {"question": "Q?", "answer": "A.", "metadata": {}},
        ]
        mock_emb_generate.return_value = [0.1]

        with (
            patch("internal.tasks.knowledge_generation.settings") as mock_settings,
            patch.object(validate_knowledge_entry, "delay") as mock_validate_delay,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.validation_enabled = True
            result = generate_knowledge_entries.run("source text", 5, "context", 1)

        assert result["created_count"] == 1
        mock_validate_delay.assert_called_once()

    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_empty_generation(self, mock_gen_entries):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        mock_gen_entries.return_value = []

        with patch("internal.tasks.knowledge_generation.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            result = generate_knowledge_entries.run("source text", 5, None, 1)

        assert result["created_count"] == 0
        assert result["entry_ids"] == []

    @patch("internal.tasks.knowledge_generation.get_sync_db_session")
    @patch("internal.services.embeddings_sync.SyncEmbeddingService.generate")
    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_skips_empty_question(self, mock_gen_entries, mock_emb_generate, mock_get_db):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_ns = MagicMock()
        mock_ns.slug = "general"
        mock_db.get.return_value = mock_ns

        mock_gen_entries.return_value = [
            {"question": "", "answer": "A.", "metadata": {}},
            {"question": "Q?", "answer": "", "metadata": {}},
            {"question": "Valid?", "answer": "Yes.", "metadata": {}},
        ]
        mock_emb_generate.return_value = [0.1]

        with patch("internal.tasks.knowledge_generation.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.validation_enabled = False
            result = generate_knowledge_entries.run("source text", 5, None, 1)

        assert result["created_count"] == 1

    @patch("internal.tasks.knowledge_generation.get_sync_db_session")
    @patch("internal.services.embeddings_sync.SyncEmbeddingService.generate")
    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_embedding_failure_continues(self, mock_gen_entries, mock_emb_generate, mock_get_db):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_ns = MagicMock()
        mock_ns.slug = "general"
        mock_db.get.return_value = mock_ns

        mock_gen_entries.return_value = [
            {"question": "Q?", "answer": "A.", "metadata": {}},
        ]
        mock_emb_generate.side_effect = Exception("API error")

        with patch("internal.tasks.knowledge_generation.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.validation_enabled = False
            result = generate_knowledge_entries.run("source text", 5, None, 1)

        assert result["created_count"] == 1

    @patch("internal.tasks.knowledge_generation.get_sync_db_session")
    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_no_openai_key_skips_embeddings(self, mock_gen_entries, mock_get_db):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_ns = MagicMock()
        mock_ns.slug = "test"
        mock_db.get.return_value = mock_ns

        mock_gen_entries.return_value = [
            {"question": "Q?", "answer": "A.", "metadata": {}},
        ]

        with patch("internal.tasks.knowledge_generation.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            mock_settings.validation_enabled = False
            result = generate_knowledge_entries.run("source text", 5, None, 1)

        assert result["created_count"] == 1

    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_failure_retries(self, mock_gen_entries):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        mock_gen_entries.side_effect = RuntimeError("API down")

        with (
            patch("internal.tasks.knowledge_generation.settings") as mock_settings,
            patch.object(
                generate_knowledge_entries, "retry", side_effect=Exception("retry")
            ) as mock_retry,
        ):
            mock_settings.openai_api_key = "sk-test"
            with pytest.raises(Exception, match="retry"):
                generate_knowledge_entries.run("source text", 5, None, 1)

            mock_retry.assert_called_once()

    @patch("internal.tasks.knowledge_generation.get_sync_db_session")
    @patch("internal.services.embeddings_sync.SyncEmbeddingService.generate")
    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_namespace_not_found_uses_general(
        self, mock_gen_entries, mock_emb_generate, mock_get_db
    ):
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_db.get.return_value = None

        mock_gen_entries.return_value = [
            {"question": "Q?", "answer": "A.", "metadata": {}},
        ]
        mock_emb_generate.return_value = [0.1]

        with patch("internal.tasks.knowledge_generation.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.validation_enabled = False
            result = generate_knowledge_entries.run("source text", 5, None, 999)

        assert result["namespace_slug"] == "general"

    @patch("internal.tasks.knowledge_generation.get_sync_db_session")
    @patch("internal.services.embeddings_sync.SyncEmbeddingService.generate")
    @patch(
        "internal.services.knowledge_generator_sync.SyncKnowledgeGeneratorService.generate_entries"
    )
    def test_validation_dispatch_failure_still_succeeds(
        self, mock_gen_entries, mock_emb_generate, mock_get_db
    ):
        from internal.tasks.knowledge_generation import generate_knowledge_entries
        from internal.tasks.knowledge_validation import validate_knowledge_entry

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_ns = MagicMock()
        mock_ns.slug = "general"
        mock_db.get.return_value = mock_ns

        mock_gen_entries.return_value = [
            {"question": "Q?", "answer": "A.", "metadata": {}},
        ]
        mock_emb_generate.return_value = [0.1]

        with (
            patch("internal.tasks.knowledge_generation.settings") as mock_settings,
            patch.object(
                validate_knowledge_entry,
                "delay",
                side_effect=Exception("Redis down"),
            ),
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.validation_enabled = True
            result = generate_knowledge_entries.run("source text", 5, None, 1)

        assert result["created_count"] == 1
