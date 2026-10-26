# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.cleanup — CleanupRepository (100% mocked, sync)."""

import uuid
from unittest.mock import MagicMock

from auth.db.repositories.cleanup import CleanupRepository


def make_scalars_result(rows: list) -> MagicMock:
    """Build a sync Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


class TestDeleteWebhookDeliveriesOverCap:
    def test_no_overflow_returns_zero_without_delete(self):
        repo = CleanupRepository()
        db = MagicMock()
        db.execute.return_value = make_scalars_result([])

        assert repo.delete_webhook_deliveries_over_cap(db, uuid.uuid4(), 100) == 0
        # Only the SELECT ran — no DELETE was issued.
        assert db.execute.call_count == 1

    def test_deletes_overflow_rows(self):
        repo = CleanupRepository()
        db = MagicMock()
        overflow = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        delete_result = MagicMock()
        delete_result.rowcount = 3
        db.execute.side_effect = [make_scalars_result(overflow), delete_result]

        assert repo.delete_webhook_deliveries_over_cap(db, uuid.uuid4(), 10) == 3
        assert db.execute.call_count == 2

    def test_null_rowcount_becomes_zero(self):
        repo = CleanupRepository()
        db = MagicMock()
        delete_result = MagicMock()
        delete_result.rowcount = None
        db.execute.side_effect = [make_scalars_result([uuid.uuid4()]), delete_result]

        assert repo.delete_webhook_deliveries_over_cap(db, uuid.uuid4(), 1) == 0
