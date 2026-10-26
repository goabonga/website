# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for task management routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_team_mock():
    team = MagicMock()
    team.id = uuid4()
    return team


def _make_task_mock(team_id, *, status="pending", agent_id=None, title="Test task"):
    task = MagicMock()
    task.id = uuid4()
    task.team_id = team_id
    task.workflow_id = None
    task.agent_id = agent_id
    task.title = title
    task.description = ""
    task.status = status
    task.priority = 0
    task.input_data = {}
    task.output_data = {}
    task.created_at = datetime.now(UTC)
    task.updated_at = datetime.now(UTC)
    return task


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_pending(self, auth_client: AsyncClient, mock_db_session):
        """Task without agent_id stays pending, no celery dispatch."""
        team_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks",
            json={"title": "Review PR"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Review PR"
        assert data["status"] == "pending"
        assert data["agent_id"] is None

    @pytest.mark.asyncio
    async def test_create_task_assigned_with_agent(self, auth_client: AsyncClient, mock_db_session):
        """Task with agent_id is assigned and dispatched immediately."""
        team_id = uuid4()
        agent_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("team.tasks.agent_runner.run_agent_task") as mock_run:
            mock_run.delay = MagicMock()

            response = await auth_client.post(
                f"/platform/{team_id}/tasks",
                json={
                    "title": "Analyze logs",
                    "agent_id": str(agent_id),
                    "input_data": {"prompt": "Check the logs"},
                    "priority": 50,
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["title"] == "Analyze logs"
            assert data["status"] == "assigned"
            assert data["priority"] == 50
            mock_run.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_with_all_fields(self, auth_client: AsyncClient, mock_db_session):
        """Task with description, priority, and input_data."""
        team_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks",
            json={
                "title": "Full task",
                "description": "With all fields",
                "priority": 100,
                "input_data": {"key": "value"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "With all fields"
        assert data["priority"] == 100
        assert data["input_data"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_create_task_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Returns 404 when team does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{uuid4()}/tasks",
            json={"title": "Orphan task"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_task_requires_auth(self, client: AsyncClient):
        """Returns 401 when not authenticated."""
        response = await client.post(
            f"/platform/{uuid4()}/tasks",
            json={"title": "No auth"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_task_missing_title(self, auth_client: AsyncClient, mock_db_session):
        """Returns 422 when title is missing."""
        response = await auth_client.post(
            f"/platform/{uuid4()}/tasks",
            json={},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_task_with_workflow_id(self, auth_client: AsyncClient, mock_db_session):
        """Task can include a workflow_id."""
        team_id = uuid4()
        workflow_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks",
            json={
                "title": "Workflow step",
                "workflow_id": str(workflow_id),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["workflow_id"] == str(workflow_id)

    @pytest.mark.asyncio
    async def test_create_task_defaults(self, auth_client: AsyncClient, mock_db_session):
        """Verify default values for optional fields."""
        team_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_team_mock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks",
            json={"title": "Minimal"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["description"] == ""
        assert data["priority"] == 0
        assert data["input_data"] == {}
        assert data["output_data"] == {}


class TestCancelTask:
    @pytest.mark.asyncio
    async def test_cancel_pending_task(self, auth_client: AsyncClient, mock_db_session):
        """Cancel a pending task sets status to cancelled."""
        team_id = uuid4()
        team_mock = _make_team_mock()
        task_mock = _make_task_mock(team_id, status="pending")

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=task_mock)),
            # No agent_id → skip AgentState query
            # Conversation query
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{task_mock.id}/cancel",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_assigned_task_resets_agent_state(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """Cancel an assigned task resets agent state to idle."""
        team_id = uuid4()
        agent_id = uuid4()
        team_mock = _make_team_mock()
        task_mock = _make_task_mock(
            team_id, status="assigned", agent_id=agent_id, title="Assigned task"
        )

        agent_state_mock = MagicMock()
        agent_state_mock.current_task = "Assigned task"
        agent_state_mock.state = "idle"

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=task_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=agent_state_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{task_mock.id}/cancel",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert agent_state_mock.state == "idle"
        assert agent_state_mock.current_task == ""

    @pytest.mark.asyncio
    async def test_cancel_in_progress_task_cancels_conversation(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """Cancel an in_progress task also cancels the active conversation."""
        team_id = uuid4()
        agent_id = uuid4()
        team_mock = _make_team_mock()
        task_mock = _make_task_mock(
            team_id, status="in_progress", agent_id=agent_id, title="Running task"
        )

        agent_state_mock = MagicMock()
        agent_state_mock.current_task = "Running task"
        agent_state_mock.state = "thinking"

        conv_mock = MagicMock()
        conv_mock.status = "active"

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=task_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=agent_state_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=conv_mock)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{task_mock.id}/cancel",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert conv_mock.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_task_returns_409(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """Cannot cancel a completed task."""
        team_id = uuid4()
        team_mock = _make_team_mock()
        task_mock = _make_task_mock(team_id, status="completed")

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=task_mock)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{task_mock.id}/cancel",
        )
        assert response.status_code == 409
        assert "completed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_cancel_failed_task_returns_409(self, auth_client: AsyncClient, mock_db_session):
        """Cannot cancel a failed task."""
        team_id = uuid4()
        team_mock = _make_team_mock()
        task_mock = _make_task_mock(team_id, status="failed")

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=task_mock)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{task_mock.id}/cancel",
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_returns_409(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """Cannot cancel an already cancelled task."""
        team_id = uuid4()
        team_mock = _make_team_mock()
        task_mock = _make_task_mock(team_id, status="cancelled")

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=task_mock)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{task_mock.id}/cancel",
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_agent_state_mismatch_skips_reset(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """AgentState exists but current_task doesn't match — state not reset."""
        team_id = uuid4()
        agent_id = uuid4()
        team_mock = _make_team_mock()
        task_mock = _make_task_mock(
            team_id, status="in_progress", agent_id=agent_id, title="My task"
        )

        agent_state_mock = MagicMock()
        agent_state_mock.current_task = "Some other task"
        agent_state_mock.state = "thinking"

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=task_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=agent_state_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{task_mock.id}/cancel",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        # State NOT reset because current_task doesn't match
        assert agent_state_mock.state == "thinking"

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Returns 404 when task does not exist."""
        team_id = uuid4()
        team_mock = _make_team_mock()

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=team_mock)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        mock_db_session.execute = AsyncMock(side_effect=results)

        response = await auth_client.post(
            f"/platform/{team_id}/tasks/{uuid4()}/cancel",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_team_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Returns 404 when team does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await auth_client.post(
            f"/platform/{uuid4()}/tasks/{uuid4()}/cancel",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_task_requires_auth(self, client: AsyncClient):
        """Returns 401 when not authenticated."""
        response = await client.post(
            f"/platform/{uuid4()}/tasks/{uuid4()}/cancel",
        )
        assert response.status_code == 401
