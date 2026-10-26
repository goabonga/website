# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/schemas/."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from team.schemas import (
    AgentCreate,
    AgentUpdate,
    ConversationCreate,
    MemoryEntryCreate,
    MessageCreate,
    TaskCreate,
    TeamCreate,
    TeamUpdate,
    UsageBatchReport,
    UsageReport,
    WorkflowCreate,
    WorkflowUpdate,
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


class TestWorkflowSchemas:
    def test_workflow_create_valid(self):
        data = WorkflowCreate(name="Deploy Pipeline")
        assert data.name == "Deploy Pipeline"
        assert data.steps == {}

    def test_workflow_update_partial(self):
        data = WorkflowUpdate(status="active")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"status": "active"}


class TestTaskSchemas:
    def test_task_create_valid(self):
        data = TaskCreate(title="Review PR #42")
        assert data.title == "Review PR #42"
        assert data.priority == 0

    def test_task_create_with_agent(self):
        agent_id = uuid4()
        data = TaskCreate(title="Fix bug", agent_id=agent_id)
        assert data.agent_id == agent_id


class TestUsageSchemas:
    def test_usage_report_valid(self):
        agent_id = uuid4()
        data = UsageReport(agent_id=agent_id, action="task.completed")
        assert data.agent_id == agent_id
        assert data.action == "task.completed"

    def test_usage_batch_report_valid(self):
        agent_id = uuid4()
        events = [UsageReport(agent_id=agent_id, action="task.completed")]
        data = UsageBatchReport(events=events)
        assert len(data.events) == 1

    def test_usage_batch_report_empty_fails(self):
        with pytest.raises(ValidationError):
            UsageBatchReport(events=[])


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
