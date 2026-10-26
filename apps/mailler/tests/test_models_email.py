# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Email and ProviderStats models."""

from mailler.models import Base, Email, EmailStatus, ProviderStats


class TestEmailStatus:
    """Email delivery statuses."""

    def test_values(self):
        assert [s.value for s in EmailStatus] == [
            "pending",
            "queued",
            "sent",
            "delivered",
            "bounced",
            "failed",
        ]

    def test_is_string_enum(self):
        assert EmailStatus.SENT == "sent"


class TestEmailTables:
    """Table definitions registered on the declarative base."""

    def test_tables_registered(self):
        assert {"emails", "provider_stats"} <= set(Base.metadata.tables)

    def test_email_columns(self):
        columns = Email.__table__.columns
        for name in ("id", "to_email", "subject", "provider", "status", "metadata"):
            assert name in columns

    def test_provider_stats_is_unique_per_day_and_provider(self):
        constraints = [c for c in ProviderStats.__table__.constraints if c.columns.keys()]
        assert any(set(c.columns.keys()) == {"date", "provider"} for c in constraints)
