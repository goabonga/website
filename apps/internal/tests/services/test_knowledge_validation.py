# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge validation orchestrator service."""

from unittest.mock import MagicMock, patch

import pytest
from internal.models.knowledge import KnowledgeEntryStatus
from internal.schemas.validation import StepResult, ValidationVerdict
from internal.services.knowledge_validation import KnowledgeValidationService


def _accept_step(name: str) -> StepResult:
    return StepResult(step=name, passed=True, verdict=ValidationVerdict.ACCEPT)


def _reject_step(name: str) -> StepResult:
    return StepResult(step=name, passed=False, verdict=ValidationVerdict.REJECT)


class TestKnowledgeValidationService:
    def _make_entry(self, entry_id=1):
        entry = MagicMock()
        entry.id = entry_id
        entry.question = "What is Python programming?"
        entry.answer = (
            "Python is a high-level, interpreted programming language known for "
            "its clear syntax and extensive standard library. It supports multiple "
            "paradigms including procedural, object-oriented, and functional programming."
        )
        entry.metadata_ = {"tags": ["python"]}
        entry.namespace_id = 1
        entry.embedding = None
        entry.status = KnowledgeEntryStatus.PENDING.value
        return entry

    @patch("internal.services.knowledge_validation.validate_retrievability")
    @patch("internal.services.knowledge_validation.validate_length")
    @patch("internal.services.knowledge_validation.validate_dedup")
    @patch("internal.services.knowledge_validation.validate_semantic")
    @patch("internal.services.knowledge_validation.validate_quality")
    @patch("internal.services.knowledge_validation.validate_cleaning")
    @patch("internal.services.knowledge_validation.validate_schema")
    def test_full_pipeline_accept(
        self,
        mock_schema,
        mock_cleaning,
        mock_quality,
        mock_semantic,
        mock_dedup,
        mock_length,
        mock_retrievability,
    ):
        mock_schema.return_value = _accept_step("schema")
        mock_cleaning.return_value = StepResult(
            step="cleaning",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={
                "cleaned_question": "What is Python programming?",
                "cleaned_answer": "Python is a high-level language.",
            },
        )
        mock_quality.return_value = _accept_step("quality")
        mock_semantic.return_value = _accept_step("semantic")
        mock_dedup.return_value = StepResult(
            step="dedup",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"embedding": [0.1] * 10},
        )
        mock_length.return_value = _accept_step("length")
        mock_retrievability.return_value = _accept_step("retrievability")

        entry = self._make_entry()
        mock_db = MagicMock()
        mock_db.get.return_value = entry

        service = KnowledgeValidationService()
        result = service.validate(1, mock_db)

        assert result.final_verdict == ValidationVerdict.ACCEPT
        assert len(result.steps) == 7
        assert entry.status == KnowledgeEntryStatus.ACCEPTED.value
        assert entry.validation_details is not None
        mock_db.commit.assert_called()

    @patch("internal.services.knowledge_validation.validate_schema")
    def test_early_exit_on_schema_reject(self, mock_schema):
        mock_schema.return_value = _reject_step("schema")

        entry = self._make_entry()
        mock_db = MagicMock()
        mock_db.get.return_value = entry

        service = KnowledgeValidationService()
        result = service.validate(1, mock_db)

        assert result.final_verdict == ValidationVerdict.REJECT
        assert len(result.steps) == 1
        assert entry.status == KnowledgeEntryStatus.REJECTED.value

    @patch("internal.services.knowledge_validation.validate_dedup")
    @patch("internal.services.knowledge_validation.validate_semantic")
    @patch("internal.services.knowledge_validation.validate_quality")
    @patch("internal.services.knowledge_validation.validate_cleaning")
    @patch("internal.services.knowledge_validation.validate_schema")
    def test_early_exit_on_dedup_reject(
        self,
        mock_schema,
        mock_cleaning,
        mock_quality,
        mock_semantic,
        mock_dedup,
    ):
        mock_schema.return_value = _accept_step("schema")
        mock_cleaning.return_value = StepResult(
            step="cleaning",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"cleaned_question": "Q", "cleaned_answer": "A"},
        )
        mock_quality.return_value = _accept_step("quality")
        mock_semantic.return_value = _accept_step("semantic")
        mock_dedup.return_value = _reject_step("dedup")

        entry = self._make_entry()
        mock_db = MagicMock()
        mock_db.get.return_value = entry

        service = KnowledgeValidationService()
        result = service.validate(1, mock_db)

        assert result.final_verdict == ValidationVerdict.REJECT
        assert len(result.steps) == 5  # schema, cleaning, quality, semantic, dedup

    def test_entry_not_found_raises(self):
        mock_db = MagicMock()
        mock_db.get.return_value = None

        service = KnowledgeValidationService()
        with pytest.raises(ValueError, match="not found"):
            service.validate(999, mock_db)

    @patch("internal.services.knowledge_validation.validate_schema")
    def test_entry_status_set_to_validating(self, mock_schema):
        mock_schema.return_value = _reject_step("schema")

        entry = self._make_entry()
        mock_db = MagicMock()
        mock_db.get.return_value = entry

        # Track status changes
        statuses = []
        original_commit = mock_db.commit

        def track_commit():
            statuses.append(entry.status)
            original_commit()

        mock_db.commit = track_commit

        service = KnowledgeValidationService()
        service.validate(1, mock_db)

        # First commit sets VALIDATING, second sets final status
        assert statuses[0] == KnowledgeEntryStatus.VALIDATING.value

    @patch("internal.services.knowledge_validation.validate_retrievability")
    @patch("internal.services.knowledge_validation.validate_length")
    @patch("internal.services.knowledge_validation.validate_dedup")
    @patch("internal.services.knowledge_validation.validate_semantic")
    @patch("internal.services.knowledge_validation.validate_quality")
    @patch("internal.services.knowledge_validation.validate_cleaning")
    @patch("internal.services.knowledge_validation.validate_schema")
    def test_validation_details_stored(
        self,
        mock_schema,
        mock_cleaning,
        mock_quality,
        mock_semantic,
        mock_dedup,
        mock_length,
        mock_retrievability,
    ):
        mock_schema.return_value = _accept_step("schema")
        mock_cleaning.return_value = StepResult(
            step="cleaning",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"cleaned_question": "Q", "cleaned_answer": "A"},
        )
        mock_quality.return_value = _accept_step("quality")
        mock_semantic.return_value = _accept_step("semantic")
        mock_dedup.return_value = StepResult(
            step="dedup",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"embedding": [0.1] * 10},
        )
        mock_length.return_value = _accept_step("length")
        mock_retrievability.return_value = _accept_step("retrievability")

        entry = self._make_entry()
        mock_db = MagicMock()
        mock_db.get.return_value = entry

        service = KnowledgeValidationService()
        service.validate(1, mock_db)

        assert entry.validation_details is not None
        assert "verdict" in entry.validation_details
        assert "steps" in entry.validation_details
        # Embedding should be stripped from stored details
        for step in entry.validation_details["steps"]:
            assert "embedding" not in step.get("details", {})

    @patch("internal.services.knowledge_validation.validate_retrievability")
    @patch("internal.services.knowledge_validation.validate_length")
    @patch("internal.services.knowledge_validation.validate_dedup")
    @patch("internal.services.knowledge_validation.validate_semantic")
    @patch("internal.services.knowledge_validation.validate_quality")
    @patch("internal.services.knowledge_validation.validate_cleaning")
    @patch("internal.services.knowledge_validation.validate_schema")
    def test_pipeline_without_embedding(
        self,
        mock_schema,
        mock_cleaning,
        mock_quality,
        mock_semantic,
        mock_dedup,
        mock_length,
        mock_retrievability,
    ):
        """When dedup returns no embedding, retrievability still runs without flush."""
        mock_schema.return_value = _accept_step("schema")
        mock_cleaning.return_value = StepResult(
            step="cleaning",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"cleaned_question": "Q", "cleaned_answer": "A"},
        )
        mock_quality.return_value = _accept_step("quality")
        mock_semantic.return_value = _accept_step("semantic")
        mock_dedup.return_value = StepResult(
            step="dedup",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={},  # No embedding
        )
        mock_length.return_value = _accept_step("length")
        mock_retrievability.return_value = _accept_step("retrievability")

        entry = self._make_entry()
        mock_db = MagicMock()
        mock_db.get.return_value = entry

        service = KnowledgeValidationService()
        result = service.validate(1, mock_db)

        assert result.final_verdict == ValidationVerdict.ACCEPT
        assert len(result.steps) == 7
        # flush should NOT have been called since no embedding
        mock_db.flush.assert_not_called()
