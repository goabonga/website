# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Celery knowledge validation task."""

from unittest.mock import MagicMock, patch

import pytest
from internal.schemas.validation import ValidationResult, ValidationVerdict


class TestValidateKnowledgeEntryTask:
    @patch("internal.tasks.knowledge_validation.get_sync_db_session")
    @patch("internal.tasks.knowledge_validation.KnowledgeValidationService")
    def test_success(self, MockService, mock_get_db):
        from internal.tasks.knowledge_validation import validate_knowledge_entry

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_result = ValidationResult(
            entry_id=1,
            final_verdict=ValidationVerdict.ACCEPT,
            steps=[],
            summary="All checks passed",
        )
        mock_service = MagicMock()
        mock_service.validate.return_value = mock_result
        MockService.return_value = mock_service

        # Use .run() which calls the bound task with self automatically
        result = validate_knowledge_entry.run(1)

        mock_service.validate.assert_called_once_with(1, mock_db)
        assert result["final_verdict"] == "accept"
        assert result["entry_id"] == 1

    @patch("internal.tasks.knowledge_validation.get_sync_db_session")
    @patch("internal.tasks.knowledge_validation.KnowledgeValidationService")
    def test_failure_retries(self, MockService, mock_get_db):
        from internal.tasks.knowledge_validation import validate_knowledge_entry

        mock_db = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_service = MagicMock()
        mock_service.validate.side_effect = Exception("DB error")
        MockService.return_value = mock_service

        # Patch retry on the task instance to raise Retry
        with patch.object(
            validate_knowledge_entry, "retry", side_effect=Exception("retry")
        ) as mock_retry:
            with pytest.raises(Exception, match="retry"):
                validate_knowledge_entry.run(1)

            mock_retry.assert_called_once()
