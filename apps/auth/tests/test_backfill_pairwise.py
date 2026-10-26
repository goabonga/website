# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for pairwise subject backfill Celery task."""

import uuid
from unittest.mock import MagicMock, patch

from auth.tasks.backfill_pairwise import backfill_pairwise_subjects


def _make_mock_db():
    """Create a mock DB session and context manager."""
    mock_db = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_db)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx, mock_db


class TestBackfillPairwiseSubjects:
    """Tests for backfill_pairwise_subjects task."""

    @patch("auth.tasks.backfill_pairwise.get_sync_db")
    def test_no_platform_tenant(self, mock_get_sync_db):
        """Should abort with error when no platform tenant exists."""
        mock_ctx, mock_db = _make_mock_db()
        mock_get_sync_db.return_value = mock_ctx

        # Platform tenant query returns None
        platform_result = MagicMock()
        platform_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = platform_result

        result = backfill_pairwise_subjects()

        assert result == {
            "created": 0,
            "existing": 0,
            "total": 0,
            "error": "no_platform_tenant",
        }

    @patch("auth.tasks.backfill_pairwise.get_sync_db")
    def test_no_existing_tokens(self, mock_get_sync_db):
        """Should return zeros when no access tokens exist."""
        mock_ctx, mock_db = _make_mock_db()
        mock_get_sync_db.return_value = mock_ctx

        platform_tenant_id = uuid.uuid4()

        # First call: platform tenant query
        platform_result = MagicMock()
        platform_result.scalar_one_or_none.return_value = platform_tenant_id

        # Second call: pairs query returns empty
        pairs_result = MagicMock()
        pairs_result.all.return_value = []

        mock_db.execute.side_effect = [platform_result, pairs_result]

        result = backfill_pairwise_subjects()

        assert result == {"created": 0, "existing": 0, "total": 0}

    @patch("auth.tasks.backfill_pairwise.get_sync_db")
    def test_creates_new_pairwise_subjects(self, mock_get_sync_db):
        """Should create pairwise subjects for new (user, tenant) pairs."""
        mock_ctx, mock_db = _make_mock_db()
        mock_get_sync_db.return_value = mock_ctx

        platform_tenant_id = uuid.uuid4()
        user1 = uuid.uuid4()
        user2 = uuid.uuid4()
        tenant1 = uuid.uuid4()

        # Platform tenant query
        platform_result = MagicMock()
        platform_result.scalar_one_or_none.return_value = platform_tenant_id

        # Pairs query
        pairs_result = MagicMock()
        pairs_result.all.return_value = [
            (user1, tenant1),
            (user2, tenant1),
            (user1, platform_tenant_id),
        ]

        # Insert results (all new)
        insert_result_new = MagicMock()
        insert_result_new.rowcount = 1

        mock_db.execute.side_effect = [
            platform_result,
            pairs_result,
            insert_result_new,
            insert_result_new,
            insert_result_new,
        ]

        result = backfill_pairwise_subjects()

        assert result == {"created": 3, "existing": 0, "total": 3}

    @patch("auth.tasks.backfill_pairwise.get_sync_db")
    def test_skips_existing_pairwise_subjects(self, mock_get_sync_db):
        """Should count existing pairs without error when conflict occurs."""
        mock_ctx, mock_db = _make_mock_db()
        mock_get_sync_db.return_value = mock_ctx

        platform_tenant_id = uuid.uuid4()
        user1 = uuid.uuid4()
        tenant1 = uuid.uuid4()

        # Platform tenant query
        platform_result = MagicMock()
        platform_result.scalar_one_or_none.return_value = platform_tenant_id

        # Pairs query
        pairs_result = MagicMock()
        pairs_result.all.return_value = [
            (user1, tenant1),
            (user1, platform_tenant_id),
        ]

        # First insert: already exists (ON CONFLICT DO NOTHING -> rowcount=0)
        insert_existing = MagicMock()
        insert_existing.rowcount = 0

        # Second insert: new
        insert_new = MagicMock()
        insert_new.rowcount = 1

        mock_db.execute.side_effect = [
            platform_result,
            pairs_result,
            insert_existing,
            insert_new,
        ]

        result = backfill_pairwise_subjects()

        assert result == {"created": 1, "existing": 1, "total": 2}

    @patch("auth.tasks.backfill_pairwise.get_sync_db")
    def test_mixed_created_and_existing(self, mock_get_sync_db):
        """Should correctly count a mix of created and existing pairs."""
        mock_ctx, mock_db = _make_mock_db()
        mock_get_sync_db.return_value = mock_ctx

        platform_tenant_id = uuid.uuid4()

        # Platform tenant query
        platform_result = MagicMock()
        platform_result.scalar_one_or_none.return_value = platform_tenant_id

        # 5 pairs: 3 new, 2 existing
        pairs_result = MagicMock()
        pairs_result.all.return_value = [(uuid.uuid4(), uuid.uuid4()) for _ in range(5)]

        new_result = MagicMock()
        new_result.rowcount = 1
        existing_result = MagicMock()
        existing_result.rowcount = 0

        mock_db.execute.side_effect = [
            platform_result,
            pairs_result,
            new_result,
            existing_result,
            new_result,
            existing_result,
            new_result,
        ]

        result = backfill_pairwise_subjects()

        assert result == {"created": 3, "existing": 2, "total": 5}
