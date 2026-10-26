# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.analytics route handlers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import RedirectResponse
from internal.auth.models import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**kwargs):
    defaults = {
        "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "email": "test@example.com",
        "name": "Test User",
        "scopes": ["*"],
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    return req


# ---------------------------------------------------------------------------
# analytics_dashboard
# ---------------------------------------------------------------------------


class TestAnalyticsDashboard:
    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_success(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import analytics_dashboard

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_overview = AsyncMock(return_value={"visits": 100})
        mock_client.get_daily_stats = AsyncMock(return_value=[])
        mock_client.get_country_stats = AsyncMock(return_value=[])
        mock_client.get_device_stats = AsyncMock(return_value=[])
        mock_client.get_browser_stats = AsyncMock(return_value=[])
        mock_client.get_referrer_stats = AsyncMock(return_value=[])
        mock_client.get_page_stats = AsyncMock(return_value=[])
        mock_client.get_event_stats = AsyncMock(return_value=[])
        mock_client.get_ip_stats = AsyncMock(return_value=[])

        user = _make_user()
        request = _make_request(query_params={"error": "qp_err"})

        await analytics_dashboard(request, days=30, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["overview"] == {"visits": 100}
        assert ctx["days"] == 30
        assert ctx["error"] == "qp_err"

    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_custom_days(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import analytics_dashboard

        mock_settings.oauth2_client_id = "cid"
        for method_name in [
            "get_overview",
            "get_daily_stats",
            "get_country_stats",
            "get_device_stats",
            "get_browser_stats",
            "get_referrer_stats",
            "get_page_stats",
            "get_event_stats",
            "get_ip_stats",
        ]:
            setattr(mock_client, method_name, AsyncMock(return_value=[]))

        user = _make_user()
        request = _make_request()

        await analytics_dashboard(request, days=7, auth_result=user)

        mock_client.get_overview.assert_awaited_once_with(days=7)

    async def test_redirect_auth(self):
        from internal.routes.analytics import analytics_dashboard

        redirect = RedirectResponse(url="/login")
        result = await analytics_dashboard(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# campaigns_list
# ---------------------------------------------------------------------------


class TestCampaignsList:
    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_success(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import campaigns_list

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_campaigns = AsyncMock(return_value=[{"id": "c1"}])
        user = _make_user()
        request = _make_request()

        await campaigns_list(request, include_inactive=False, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["campaigns"] == [{"id": "c1"}]
        assert ctx["include_inactive"] is False

    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_include_inactive(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import campaigns_list

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_campaigns = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await campaigns_list(request, include_inactive=True, auth_result=user)

        mock_client.get_campaigns.assert_awaited_once_with(include_inactive=True)
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["include_inactive"] is True

    async def test_redirect_auth(self):
        from internal.routes.analytics import campaigns_list

        redirect = RedirectResponse(url="/login")
        result = await campaigns_list(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# campaign_detail
# ---------------------------------------------------------------------------


class TestCampaignDetail:
    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_success(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import campaign_detail

        mock_settings.oauth2_client_id = "cid"
        cid = uuid.uuid4()
        mock_client.get_campaign_detail = AsyncMock(return_value={"id": str(cid)})
        mock_client.get_campaign_pixels = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request(query_params={"success": "ok"})

        await campaign_detail(request, campaign_id=cid, days=30, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["campaign"]["id"] == str(cid)
        assert ctx["pixels"] == []
        assert ctx["success"] == "ok"

    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    async def test_not_found(self, mock_settings, mock_client):
        from internal.routes.analytics import campaign_detail

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_campaign_detail = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await campaign_detail(
            request,
            campaign_id=uuid.uuid4(),
            days=30,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.analytics import campaign_detail

        redirect = RedirectResponse(url="/login")
        result = await campaign_detail(
            MagicMock(),
            campaign_id=uuid.uuid4(),
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# campaign_delete
# ---------------------------------------------------------------------------


class TestCampaignDelete:
    @patch("internal.routes.analytics.analytics_client")
    async def test_success(self, mock_client):
        from internal.routes.analytics import campaign_delete

        mock_client.delete_campaign = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()
        cid = uuid.uuid4()

        result = await campaign_delete(request, campaign_id=cid, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.analytics.analytics_client")
    async def test_failure(self, mock_client):
        from internal.routes.analytics import campaign_delete

        mock_client.delete_campaign = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()
        cid = uuid.uuid4()

        result = await campaign_delete(request, campaign_id=cid, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.analytics import campaign_delete

        redirect = RedirectResponse(url="/login")
        result = await campaign_delete(
            MagicMock(),
            campaign_id=uuid.uuid4(),
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# campaigns_bulk_delete
# ---------------------------------------------------------------------------


class TestCampaignsBulkDelete:
    @patch("internal.routes.analytics.analytics_client")
    async def test_success_all_deleted(self, mock_client):
        from internal.routes.analytics import campaigns_bulk_delete

        mock_client.delete_campaigns_bulk = AsyncMock(return_value=(3, 0))
        user = _make_user()
        request = _make_request()
        ids = [str(uuid.uuid4()) for _ in range(3)]

        result = await campaigns_bulk_delete(
            request,
            campaign_ids=ids,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Deleted+3+campaigns+successfully" in result.headers["location"]

    @patch("internal.routes.analytics.analytics_client")
    async def test_partial_failure(self, mock_client):
        from internal.routes.analytics import campaigns_bulk_delete

        mock_client.delete_campaigns_bulk = AsyncMock(return_value=(2, 1))
        user = _make_user()
        request = _make_request()
        ids = [str(uuid.uuid4()) for _ in range(3)]

        result = await campaigns_bulk_delete(
            request,
            campaign_ids=ids,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        loc = result.headers["location"]
        assert "Deleted+2+campaigns" in loc
        assert "1+failed" in loc

    async def test_invalid_uuid(self):
        from internal.routes.analytics import campaigns_bulk_delete

        user = _make_user()
        request = _make_request()

        result = await campaigns_bulk_delete(
            request,
            campaign_ids=["not-a-uuid"],
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid" in result.headers["location"]

    @patch("internal.routes.analytics.analytics_client")
    async def test_empty_list_after_uuid_parse(self, mock_client):
        """Empty list after conversion should redirect with error.

        Note: In the current code the 'not uuids' check comes after conversion,
        so an empty input list would produce an empty uuids list.
        """
        from internal.routes.analytics import campaigns_bulk_delete

        # Pass an empty list of IDs - since no UUIDs to convert and the list is empty
        # Actually we need to pass a valid but empty-like scenario
        # The `campaign_ids: list[str] = Form(...)` means FastAPI would require at least one
        # But we are calling directly, so we pass an empty list
        mock_client.delete_campaigns_bulk = AsyncMock(return_value=(0, 0))
        user = _make_user()
        request = _make_request()

        # The code path: uuids = [] -> not uuids -> redirect
        result = await campaigns_bulk_delete(
            request,
            campaign_ids=[],
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=No+campaigns+selected" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.analytics import campaigns_bulk_delete

        redirect = RedirectResponse(url="/login")
        result = await campaigns_bulk_delete(
            MagicMock(),
            campaign_ids=[],
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# ip_stats_list
# ---------------------------------------------------------------------------


class TestIpStatsList:
    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_success(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import ip_stats_list

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_ip_stats = AsyncMock(return_value=[{"ip": "1.2.3.4"}])
        user = _make_user()
        request = _make_request()

        await ip_stats_list(request, days=30, limit=50, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["ip_stats"] == [{"ip": "1.2.3.4"}]
        assert ctx["days"] == 30
        assert ctx["limit"] == 50

    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_custom_params(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import ip_stats_list

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_ip_stats = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await ip_stats_list(request, days=7, limit=100, auth_result=user)

        mock_client.get_ip_stats.assert_awaited_once_with(days=7, limit=100)

    async def test_redirect_auth(self):
        from internal.routes.analytics import ip_stats_list

        redirect = RedirectResponse(url="/login")
        result = await ip_stats_list(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# ip_detail
# ---------------------------------------------------------------------------


class TestIpDetail:
    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    @patch("internal.routes.analytics.templates")
    async def test_success(self, mock_templates, mock_settings, mock_client):
        from internal.routes.analytics import ip_detail

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_ip_detail = AsyncMock(return_value={"ip": "1.2.3.4", "count": 10})
        user = _make_user()
        request = _make_request()

        await ip_detail(request, ip_address="1.2.3.4", days=30, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["ip"]["ip"] == "1.2.3.4"
        assert ctx["days"] == 30

    @patch("internal.routes.analytics.analytics_client")
    @patch("internal.routes.analytics.settings")
    async def test_not_found(self, mock_settings, mock_client):
        from internal.routes.analytics import ip_detail

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_ip_detail = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await ip_detail(
            request,
            ip_address="9.9.9.9",
            days=30,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.analytics import ip_detail

        redirect = RedirectResponse(url="/login")
        result = await ip_detail(
            MagicMock(),
            ip_address="1.2.3.4",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# reset_analytics
# ---------------------------------------------------------------------------


class TestResetAnalytics:
    @patch("internal.routes.analytics.analytics_client")
    async def test_success(self, mock_client):
        from internal.routes.analytics import reset_analytics

        mock_client.reset_all_analytics = AsyncMock(
            return_value={
                "sessions_deleted": 10,
                "events_deleted": 20,
                "campaigns_deleted": 5,
            }
        )
        user = _make_user()
        request = _make_request()

        result = await reset_analytics(request, auth_result=user)

        assert isinstance(result, RedirectResponse)
        loc = result.headers["location"]
        assert "success=" in loc
        assert "10+sessions" in loc
        assert "20+events" in loc
        assert "5+campaigns" in loc

    @patch("internal.routes.analytics.analytics_client")
    async def test_success_with_missing_keys(self, mock_client):
        from internal.routes.analytics import reset_analytics

        # Return a truthy dict but with missing keys (code uses .get with default 0)
        mock_client.reset_all_analytics = AsyncMock(return_value={"ok": True})
        user = _make_user()
        request = _make_request()

        result = await reset_analytics(request, auth_result=user)

        assert isinstance(result, RedirectResponse)
        loc = result.headers["location"]
        assert "0+sessions" in loc

    @patch("internal.routes.analytics.analytics_client")
    async def test_failure(self, mock_client):
        from internal.routes.analytics import reset_analytics

        mock_client.reset_all_analytics = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await reset_analytics(request, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.analytics import reset_analytics

        redirect = RedirectResponse(url="/login")
        result = await reset_analytics(MagicMock(), auth_result=redirect)
        assert result is redirect
