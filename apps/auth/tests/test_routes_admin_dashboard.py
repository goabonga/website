# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.admin.dashboard — the admin landing page."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_user

MODULE = "auth.api.routes.admin.dashboard"


class TestAdminDashboard:
    @pytest.mark.asyncio
    async def test_renders_aggregate_stats(self):
        from auth.api.routes.admin.dashboard import admin_dashboard

        templates = MagicMock()
        templates.TemplateResponse.return_value = MagicMock()

        user_service = AsyncMock()
        # total, active, today, week, month
        user_service.count = AsyncMock(side_effect=[120, 100, 3, 12, 40])
        session_service = AsyncMock()
        session_service.count_active = AsyncMock(return_value=17)
        client_service = AsyncMock()
        client_service.count = AsyncMock(side_effect=[9, 7])

        request = MagicMock()
        auth = (make_user(), [MagicMock()])

        with (
            patch(f"{MODULE}.get_templates", return_value=templates),
            patch(f"{MODULE}.role_service.count", AsyncMock(return_value=5)),
            patch(f"{MODULE}.get_user_admin_permissions", return_value={"can_view": True}),
        ):
            result = await admin_dashboard(
                request, AsyncMock(), auth, user_service, session_service, client_service
            )

        assert result is templates.TemplateResponse.return_value
        context = templates.TemplateResponse.call_args.kwargs["context"]
        stats = context["stats"]
        assert stats["total_users"] == 120
        assert stats["active_users"] == 100
        assert stats["inactive_users"] == 20
        assert stats["new_users_today"] == 3
        assert stats["new_users_week"] == 12
        assert stats["new_users_month"] == 40
        assert stats["active_sessions"] == 17
        assert stats["total_clients"] == 9
        assert stats["active_clients"] == 7
        assert stats["total_roles"] == 5
        assert context["active_section"] == "dashboard"
        assert context["permissions"] == {"can_view": True}
