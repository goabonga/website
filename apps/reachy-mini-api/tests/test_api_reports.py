# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for reachy_mini_api/api/reports.py."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reachy_mini_api.auth.dependencies import AuthContext
from reachy_mini_api.auth.jwks import jwks_manager
from reachy_mini_api.auth.models import User
from reachy_mini_api.main import app


@pytest.fixture
def mock_user():
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        name="Test",
        scopes=["reachy:reports:read", "reachy:notifications:read"],
        client_id="test-client",
    )
    return AuthContext(user=user)


class TestDailyReport:
    """Tests for GET /api/reports/daily endpoint."""

    @pytest.mark.asyncio
    async def test_get_daily_report(self, mock_user):
        """Return daily report."""
        from reachy_mini_api.api.reports import get_daily_report

        with patch("reachy_mini_api.api.reports.log_action"):
            result = await get_daily_report(auth=mock_user)

        assert result.date is not None
        assert result.summary == "Today is looking productive!"
        assert result.tasks_completed == 5
        assert result.tasks_pending == 3
        assert len(result.notifications) == 2
        assert result.weather == "Sunny, 22\u00b0C"
        assert len(result.calendar_events) == 2

    @pytest.mark.asyncio
    async def test_daily_report_logs_action(self, mock_user):
        """Log action when getting daily report."""
        from reachy_mini_api.api.reports import get_daily_report

        with patch("reachy_mini_api.api.reports.log_action") as mock_log:
            await get_daily_report(auth=mock_user)
            mock_log.assert_called_once_with(
                mock_log.call_args[0][0], "get_daily_report", user_id=mock_user.user_id
            )


class TestQuickUpdate:
    """Tests for GET /api/reports/quick endpoint."""

    @pytest.mark.asyncio
    async def test_get_quick_update(self, mock_user):
        """Return quick update."""
        from reachy_mini_api.api.reports import get_quick_update

        with patch("reachy_mini_api.api.reports.log_action"):
            result = await get_quick_update(auth=mock_user)

        assert result.message == "All systems running smoothly."
        assert result.priority == "normal"
        assert result.category == "status"

    @pytest.mark.asyncio
    async def test_quick_update_logs_action(self, mock_user):
        """Log action when getting quick update."""
        from reachy_mini_api.api.reports import get_quick_update

        with patch("reachy_mini_api.api.reports.log_action") as mock_log:
            await get_quick_update(auth=mock_user)
            mock_log.assert_called_once()


class TestNotifications:
    """Tests for GET /api/reports/notifications endpoint."""

    @pytest.mark.asyncio
    async def test_get_notifications(self, mock_user):
        """Return notifications."""
        from reachy_mini_api.api.reports import get_notifications

        with patch("reachy_mini_api.api.reports.log_action"):
            result = await get_notifications(auth=mock_user)

        assert result["count"] == 2
        assert len(result["notifications"]) == 2
        assert result["notifications"][0]["message"] == "New task assigned"
        assert result["notifications"][1]["message"] == "Build completed"

    @pytest.mark.asyncio
    async def test_notifications_logs_action(self, mock_user):
        """Log action when getting notifications."""
        from reachy_mini_api.api.reports import get_notifications

        with patch("reachy_mini_api.api.reports.log_action") as mock_log:
            await get_notifications(auth=mock_user)
            mock_log.assert_called_once()


class TestModels:
    """Tests for Pydantic models."""

    def test_daily_report_model(self):
        """Create DailyReport model."""
        from reachy_mini_api.api.reports import DailyReport

        report = DailyReport(
            date="2024-01-01",
            summary="Test",
            tasks_completed=1,
            tasks_pending=2,
            notifications=["note1"],
        )
        assert report.date == "2024-01-01"
        assert report.weather is None
        assert report.calendar_events == []

    def test_quick_update_model_defaults(self):
        """Create QuickUpdate with defaults."""
        from reachy_mini_api.api.reports import QuickUpdate

        update = QuickUpdate(message="Hello")
        assert update.priority == "normal"
        assert update.category == "general"


class TestReportsRoutes:
    """HTTP behaviour of the reports routes, with the JWT validation faked."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def _get(self, client, path, scope):
        claims = {"sub": str(uuid4()), "scope": scope}
        with patch.object(jwks_manager, "validate_token", AsyncMock(return_value=claims)):
            return client.get(path, headers={"Authorization": "Bearer a.b.c"})

    def test_routes_are_mounted_under_api(self):
        paths = set(app.openapi()["paths"])
        assert {
            "/api/reports/daily",
            "/api/reports/quick",
            "/api/reports/notifications",
        } <= paths

    @pytest.mark.parametrize(
        "path",
        ["/api/reports/daily", "/api/reports/quick", "/api/reports/notifications"],
    )
    def test_requires_a_token(self, client, path):
        assert client.get(path).status_code == 401

    def test_daily_report_with_scope(self, client):
        response = self._get(client, "/api/reports/daily", "reachy:reports:read")
        assert response.status_code == 200
        assert response.json()["tasks_completed"] == 5

    def test_quick_update_with_scope(self, client):
        response = self._get(client, "/api/reports/quick", "reachy:reports:read")
        assert response.status_code == 200
        assert response.json()["category"] == "status"

    def test_notifications_with_scope(self, client):
        response = self._get(client, "/api/reports/notifications", "reachy:notifications:read")
        assert response.status_code == 200
        assert response.json()["count"] == 2

    def test_notifications_need_their_own_scope(self, client):
        response = self._get(client, "/api/reports/notifications", "reachy:reports:read")
        assert response.status_code == 403

    def test_reports_wildcard_scope(self, client):
        response = self._get(client, "/api/reports/daily", "reachy:*")
        assert response.status_code == 200
