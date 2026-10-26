# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/schemas/."""

from uuid import uuid4

from team.schemas import (
    AgentCreate,
    AgentUpdate,
    ConversationCreate,
    MemoryEntryCreate,
    MessageCreate,
    TeamCreate,
    TeamUpdate,
)


class TestAgentSchemas:
    def test_agent_create_valid(self):
        data = AgentCreate(name="DevAgent", role="developer")
        assert data.name == "DevAgent"
        assert data.role == "developer"
        assert data.model == "gpt-4o"

    def test_agent_update_partial(self):
        data = AgentUpdate(name="NewName")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"name": "NewName"}


class TestTeamSchemas:
    def test_team_create_valid(self):
        data = TeamCreate(name="Engineering", slug="engineering")
        assert data.name == "Engineering"
        assert data.slug == "engineering"

    def test_team_update_partial(self):
        data = TeamUpdate(is_active=False)
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"is_active": False}


class TestMessageSchemas:
    def test_message_create_valid(self):
        agent_id = uuid4()
        data = MessageCreate(agent_id=agent_id, text="Hello")
        assert data.agent_id == agent_id
        assert data.type == "message"
        assert data.visibility == "public"


class TestConversationSchemas:
    def test_conversation_create_valid(self):
        data = ConversationCreate(slug="general", title="General Chat")
        assert data.slug == "general"
        assert data.type == "general"


class TestMemorySchemas:
    def test_memory_entry_create_valid(self):
        data = MemoryEntryCreate(content="Important fact")
        assert data.content == "Important fact"
        assert data.agent_id is None
