# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/models/."""

from team.models import (
    Agent,
    AgentState,
    Base,
    Conversation,
    ConversationParticipant,
    ExecutionLog,
    MemoryEntry,
    Message,
    Task,
    Team,
    Workflow,
)


class TestModelsImport:
    """Tests that all models are importable and correctly configured."""

    def test_base_is_importable(self):
        assert Base is not None

    def test_team_tablename(self):
        assert Team.__tablename__ == "teams"

    def test_agent_tablename(self):
        assert Agent.__tablename__ == "agents"

    def test_workflow_tablename(self):
        assert Workflow.__tablename__ == "workflows"

    def test_task_tablename(self):
        assert Task.__tablename__ == "tasks"

    def test_execution_log_tablename(self):
        assert ExecutionLog.__tablename__ == "execution_logs"

    def test_conversation_tablename(self):
        assert Conversation.__tablename__ == "conversations"

    def test_message_tablename(self):
        assert Message.__tablename__ == "messages"

    def test_agent_state_tablename(self):
        assert AgentState.__tablename__ == "agent_states"

    def test_memory_entry_tablename(self):
        assert MemoryEntry.__tablename__ == "memory_entries"

    def test_conversation_participant_tablename(self):
        assert ConversationParticipant.__tablename__ == "conversation_participants"


def test_all_models_registered_in_metadata():
    """All model tables should be registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "agent_states",
        "agents",
        "conversation_participants",
        "conversations",
        "execution_logs",
        "memory_entries",
        "messages",
        "skills",
        "tasks",
        "teams",
        "workflows",
    }
    assert expected.issubset(table_names)
