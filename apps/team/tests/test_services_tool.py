# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for tool service."""

from unittest.mock import AsyncMock, MagicMock

import team.services.tools  # noqa: F401 — triggers tool registration
from team.services.tool_service import ToolService


class TestToolRegistry:
    def test_register_and_lookup(self):
        """Registered tools appear in the registry."""
        # Tools are registered at import time via decorators
        assert "search_memory" in ToolService._registry
        assert "create_task" in ToolService._registry
        assert "http_request" in ToolService._registry
        # New tools
        assert "service_call" in ToolService._registry
        assert "team_status" in ToolService._registry
        assert "save_memory" in ToolService._registry
        assert "update_memory" in ToolService._registry
        assert "delete_memory" in ToolService._registry
        # Billing tools
        assert "billing_list_subscriptions" in ToolService._registry
        assert "billing_get_customer" in ToolService._registry
        assert "billing_report_usage" in ToolService._registry
        assert "billing_get_subscription" in ToolService._registry
        # Mailler tools
        assert "mailler_send_email" in ToolService._registry
        assert "mailler_get_stats" in ToolService._registry
        assert "mailler_list_templates" in ToolService._registry
        assert "mailler_start_campaign" in ToolService._registry
        # Analytics tools
        assert "analytics_overview" in ToolService._registry
        assert "analytics_pages" in ToolService._registry
        assert "analytics_campaigns" in ToolService._registry
        # Auth tools
        assert "auth_list_users" in ToolService._registry
        assert "auth_list_clients" in ToolService._registry
        assert "auth_list_roles" in ToolService._registry

    def test_get_tool_definitions_known(self):
        service = ToolService()
        defs = service.get_tool_definitions(["search_memory"])
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] == "search_memory"

    def test_get_tool_definitions_multiple(self):
        service = ToolService()
        defs = service.get_tool_definitions(["search_memory", "create_task"])
        assert len(defs) == 2

    def test_get_tool_definitions_unknown(self):
        service = ToolService()
        defs = service.get_tool_definitions(["nonexistent"])
        assert len(defs) == 0


class TestToolExecution:
    async def test_execute_registered_tool(self):
        service = ToolService()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        context = {"db": mock_session, "team_id": "team-1"}
        result = await service.execute_tool("search_memory", {"query": "test"}, context)
        assert "results" in result

    async def test_execute_unknown_tool(self):
        service = ToolService()
        result = await service.execute_tool("nonexistent", {}, {})
        assert "error" in result

    async def test_execute_create_task(self):
        service = ToolService()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        context = {"db": mock_session, "team_id": "team-1"}
        result = await service.execute_tool("create_task", {"title": "Sub-task"}, context)
        assert result["status"] == "pending"
        assert result["title"] == "Sub-task"
        mock_session.add.assert_called_once()

    async def test_create_task_injects_creator_agent(self):
        service = ToolService()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        # First execute call returns agent name, no role query needed
        name_result = MagicMock()
        name_result.scalar_one_or_none.return_value = "architect"
        mock_session.execute = AsyncMock(return_value=name_result)

        context = {"db": mock_session, "team_id": "team-1", "agent_id": "agent-42"}
        result = await service.execute_tool("create_task", {"title": "Delegated work"}, context)
        assert result["status"] == "pending"
        assert result["title"] == "Delegated work"
        # Verify creator info was injected into the task's input_data
        added_task = mock_session.add.call_args[0][0]
        assert added_task.input_data["created_by_agent_id"] == "agent-42"
        assert added_task.input_data["created_by_agent_name"] == "architect"

    async def test_create_task_creator_agent_not_found(self):
        service = ToolService()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        # Agent name query returns None (agent deleted or missing)
        name_result = MagicMock()
        name_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=name_result)

        context = {"db": mock_session, "team_id": "team-1", "agent_id": "agent-99"}
        result = await service.execute_tool("create_task", {"title": "Orphan task"}, context)
        assert result["status"] == "pending"
        added_task = mock_session.add.call_args[0][0]
        assert added_task.input_data["created_by_agent_id"] == "agent-99"
        assert "created_by_agent_name" not in added_task.input_data

    async def test_create_task_with_valid_role(self):
        service = ToolService()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        # Mock the agent role query
        role_result = MagicMock()
        role_result.all.return_value = [("developer",), ("qa",), ("security",)]
        mock_session.execute = AsyncMock(return_value=role_result)

        context = {"db": mock_session, "team_id": "team-1"}
        result = await service.execute_tool(
            "create_task",
            {"title": "Code review", "input_data": {"role": "developer"}},
            context,
        )
        assert result["status"] == "pending"
        assert result["title"] == "Code review"
        mock_session.add.assert_called_once()

    async def test_create_task_with_invalid_role(self):
        service = ToolService()
        mock_session = AsyncMock()
        # Mock the agent role query
        role_result = MagicMock()
        role_result.all.return_value = [("developer",), ("qa",), ("security",)]
        mock_session.execute = AsyncMock(return_value=role_result)

        context = {"db": mock_session, "team_id": "team-1"}
        result = await service.execute_tool(
            "create_task",
            {"title": "Audit", "input_data": {"role": "security_engineer"}},
            context,
        )
        assert "error" in result
        assert "security_engineer" in result["error"]
        assert "available_roles" in result
        assert "security" in result["available_roles"]
        mock_session.add.assert_not_called()

    async def test_execute_http_request(self):
        service = ToolService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        service._client = mock_client

        context = {"tool_service": service}
        result = await service.execute_tool("http_request", {"url": "https://example.com"}, context)
        assert result["status_code"] == 200
        assert result["body"] == "OK"
        await service.close()


class TestFormatToolResult:
    async def test_format_result(self):
        service = ToolService()
        msg = await service.format_tool_result("call_123", {"answer": 42})
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_123"
        assert msg["content"] == {"answer": 42}


class TestToolServiceLifecycle:
    def test_init_client_is_none(self):
        service = ToolService()
        assert service._client is None

    async def test_get_client_creates_client(self):
        service = ToolService()
        client = await service.get_client()
        assert client is not None
        await service.close()

    async def test_close_without_client(self):
        service = ToolService()
        await service.close()
        assert service._client is None
