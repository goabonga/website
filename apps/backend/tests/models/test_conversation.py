# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the conversation and usage models."""

import uuid

from backend.database import Base
from backend.models import Conversation, Message, UsageLog


class TestConversationModel:
    """Tests for Conversation."""

    def test_table_and_columns(self):
        """The conversations table has the expected columns."""
        table = Conversation.__table__
        assert table.name == "conversations"
        assert set(table.columns.keys()) == {
            "id",
            "user_id",
            "session_id",
            "title",
            "summary",
            "created_at",
            "updated_at",
            "archived_at",
        }

    def test_owner_columns_are_nullable_and_indexed(self):
        """A conversation belongs to a user or to an anonymous session."""
        table = Conversation.__table__
        for name in ("user_id", "session_id", "archived_at"):
            assert table.columns[name].nullable is True
            assert table.columns[name].index is True

    def test_id_default_is_uuid(self):
        """The primary key defaults to a fresh UUID."""
        default = Conversation.__table__.columns["id"].default
        assert isinstance(default.arg(None), uuid.UUID)

    def test_relationships_cascade_deletes(self):
        """Deleting a conversation deletes its messages and usage logs."""
        for name in ("messages", "usage_logs"):
            rel = Conversation.__mapper__.relationships[name]
            assert "delete-orphan" in rel.cascade


class TestMessageModel:
    """Tests for Message."""

    def test_table_and_columns(self):
        """The messages table has the expected columns."""
        table = Message.__table__
        assert table.name == "messages"
        assert set(table.columns.keys()) == {
            "id",
            "conversation_id",
            "role",
            "content",
            "created_at",
        }

    def test_role_and_content_are_required(self):
        """Role and content cannot be null."""
        table = Message.__table__
        assert table.columns["role"].nullable is False
        assert table.columns["content"].nullable is False

    def test_foreign_key_cascades(self):
        """The message foreign key deletes with the conversation."""
        (fk,) = Message.__table__.columns["conversation_id"].foreign_keys
        assert fk.target_fullname == "conversations.id"
        assert fk.ondelete == "CASCADE"


class TestUsageLogModel:
    """Tests for UsageLog."""

    def test_table_and_columns(self):
        """The usage_logs table has the expected columns."""
        table = UsageLog.__table__
        assert table.name == "usage_logs"
        assert set(table.columns.keys()) == {
            "id",
            "user_id",
            "conversation_id",
            "prompt_tokens",
            "completion_tokens",
            "model",
            "created_at",
        }

    def test_token_counters_default_to_zero(self):
        """Token counters default to zero."""
        table = UsageLog.__table__
        assert table.columns["prompt_tokens"].default.arg == 0
        assert table.columns["completion_tokens"].default.arg == 0


def test_tables_are_registered_on_base():
    """All three tables are part of the shared metadata."""
    assert {"conversations", "messages", "usage_logs"} <= set(Base.metadata.tables)
