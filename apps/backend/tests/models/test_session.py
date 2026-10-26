# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the AnonymousSession model."""

from backend.database import Base
from backend.models import AnonymousSession


class TestAnonymousSessionModel:
    """Tests for AnonymousSession."""

    def test_table_and_columns(self):
        """The anonymous_sessions table has the expected columns."""
        table = AnonymousSession.__table__
        assert table.name == "anonymous_sessions"
        assert set(table.columns.keys()) == {"id", "session_id", "created_at", "last_active"}

    def test_session_id_is_unique_and_indexed(self):
        """A client-generated session id is stored once."""
        column = AnonymousSession.__table__.columns["session_id"]
        assert column.unique is True
        assert column.index is True
        assert column.nullable is False
        assert column.type.length == 36

    def test_registered_on_base(self):
        """The table is part of the shared metadata."""
        assert "anonymous_sessions" in Base.metadata.tables
