# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.models module."""

from analytics.models import Base, Event, Session


class TestModelImports:
    """Tests that all models are properly exported."""

    def test_base_exists(self):
        assert Base is not None

    def test_session_model(self):
        assert Session.__tablename__ == "analytics_sessions"

    def test_event_model(self):
        assert Event.__tablename__ == "analytics_events"


class TestSessionModel:
    """Tests for Session model."""

    def test_repr(self):
        session = Session()
        session.session_id = "test-123"
        assert repr(session) == "<Session test-123>"


class TestEventModel:
    """Tests for Event model."""

    def test_repr(self):
        from datetime import datetime

        event = Event()
        event.event_type = "page_view"
        event.timestamp = datetime(2025, 1, 1)
        assert "page_view" in repr(event)


class TestSchema:
    """Tests for the table definitions."""

    def test_tables_registered_on_base(self):
        assert {"analytics_sessions", "analytics_events"} <= set(Base.metadata.tables)

    def test_session_id_is_unique_and_indexed(self):
        column = Session.__table__.c.session_id
        assert column.unique
        assert column.index

    def test_session_timestamps_have_defaults(self):
        table = Session.__table__
        assert table.c.first_seen.default is not None
        assert table.c.last_seen.default is not None
        assert table.c.last_seen.onupdate is not None

    def test_event_references_session_with_cascade(self):
        (foreign_key,) = Event.__table__.c.session_id.foreign_keys
        assert foreign_key.column.table.name == "analytics_sessions"
        assert foreign_key.ondelete == "CASCADE"

    def test_session_events_relationship_cascades_deletes(self):
        relationship = Session.__mapper__.relationships["events"]
        assert "delete-orphan" in relationship.cascade
        assert relationship.back_populates == "session"

    def test_event_composite_index(self):
        names = {index.name for index in Event.__table__.indexes}
        assert "ix_analytics_events_type_timestamp" in names
