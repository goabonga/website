# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.email_campaigns module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse, RedirectResponse
from internal.auth.models import User
from internal.routes.email_campaigns import (
    CAMPAIGN_STATUSES,
    SEND_STATUSES,
    email_campaign_create,
    email_campaign_delete,
    email_campaign_detail,
    email_campaign_edit,
    email_campaign_new,
    email_campaign_pause,
    email_campaign_resume,
    email_campaign_send,
    email_campaign_stats,
    email_campaign_update,
    email_campaigns_bulk_delete,
    email_campaigns_list,
    parse_campaigns,
    parse_datetime_fields,
    parse_sends,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_user():
    return User(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        email="test@example.com",
        name="Test",
        scopes=["*"],
    )


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    req.json = AsyncMock(return_value={})
    return req


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestParseDatetimeFields:
    """Tests for parse_datetime_fields helper."""

    def test_parses_iso_string(self):
        item = {"created_at": "2024-01-15T10:30:00Z"}
        result = parse_datetime_fields(item, ["created_at"])
        assert isinstance(result["created_at"], datetime)

    def test_parses_iso_string_without_z(self):
        item = {"created_at": "2024-01-15T10:30:00+00:00"}
        result = parse_datetime_fields(item, ["created_at"])
        assert isinstance(result["created_at"], datetime)

    def test_skips_missing_field(self):
        item = {"name": "test"}
        result = parse_datetime_fields(item, ["created_at"])
        assert "created_at" not in result

    def test_skips_none_value(self):
        item = {"created_at": None}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is None

    def test_skips_non_string_value(self):
        dt = datetime(2024, 1, 15, tzinfo=UTC)
        item = {"created_at": dt}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is dt

    def test_suppresses_invalid_format(self):
        item = {"created_at": "not-a-date"}
        result = parse_datetime_fields(item, ["created_at"])
        # Value remains unchanged since parsing failed
        assert result["created_at"] == "not-a-date"

    def test_multiple_fields(self):
        item = {
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-02-20T12:00:00Z",
        }
        result = parse_datetime_fields(item, ["created_at", "updated_at"])
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)

    def test_empty_string_value(self):
        item = {"created_at": ""}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] == ""


class TestParseCampaigns:
    """Tests for parse_campaigns helper."""

    def test_parses_list_of_campaigns(self):
        campaigns = [
            {"created_at": "2024-01-15T10:30:00Z", "name": "Campaign 1"},
            {"created_at": "2024-02-20T12:00:00Z", "name": "Campaign 2"},
        ]
        result = parse_campaigns(campaigns)
        assert len(result) == 2
        assert isinstance(result[0]["created_at"], datetime)
        assert isinstance(result[1]["created_at"], datetime)

    def test_empty_list(self):
        assert parse_campaigns([]) == []

    def test_all_datetime_fields(self):
        campaign = {
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
            "scheduled_at": "2024-01-16T10:00:00Z",
            "started_at": "2024-01-16T11:00:00Z",
            "completed_at": "2024-01-16T12:00:00Z",
        }
        result = parse_campaigns([campaign])
        for field in ["created_at", "updated_at", "scheduled_at", "started_at", "completed_at"]:
            assert isinstance(result[0][field], datetime)


class TestParseSends:
    """Tests for parse_sends helper."""

    def test_parses_list_of_sends(self):
        sends = [
            {"created_at": "2024-01-15T10:00:00Z", "sent_at": "2024-01-15T10:01:00Z"},
        ]
        result = parse_sends(sends)
        assert len(result) == 1
        assert isinstance(result[0]["created_at"], datetime)
        assert isinstance(result[0]["sent_at"], datetime)

    def test_empty_list(self):
        assert parse_sends([]) == []

    def test_all_datetime_fields(self):
        send = {
            "created_at": "2024-01-15T10:00:00Z",
            "queued_at": "2024-01-15T10:00:00Z",
            "sent_at": "2024-01-15T10:01:00Z",
            "delivered_at": "2024-01-15T10:02:00Z",
            "opened_at": "2024-01-15T11:00:00Z",
            "clicked_at": "2024-01-15T11:30:00Z",
            "bounced_at": "2024-01-15T10:03:00Z",
        }
        result = parse_sends([send])
        for field in [
            "created_at",
            "queued_at",
            "sent_at",
            "delivered_at",
            "opened_at",
            "clicked_at",
            "bounced_at",
        ]:
            assert isinstance(result[0][field], datetime)


class TestModuleLevelConstants:
    """Tests for module-level constants."""

    def test_campaign_statuses(self):
        assert CAMPAIGN_STATUSES == [
            "draft",
            "scheduled",
            "sending",
            "paused",
            "completed",
            "failed",
        ]

    def test_send_statuses(self):
        assert SEND_STATUSES == [
            "pending",
            "queued",
            "sent",
            "delivered",
            "opened",
            "clicked",
            "bounced",
            "complained",
            "failed",
        ]


# ---------------------------------------------------------------------------
# Route handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmailCampaignsList:
    """Tests for email_campaigns_list handler."""

    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request(query_params={"success": "ok", "error": None})
        mock_mc.get_campaigns = AsyncMock(
            return_value={
                "items": [{"created_at": "2024-01-15T10:00:00Z", "name": "C1"}],
                "total": 1,
                "pages": 1,
            }
        )
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_campaigns_list(
            request=req,
            page=1,
            search=None,
            status=None,
            auth_result=user,
        )

        assert result == "rendered"
        mock_mc.get_campaigns.assert_awaited_once_with(
            page=1,
            page_size=20,
            status=None,
            search=None,
        )
        ctx = mock_tpl.TemplateResponse.call_args
        assert ctx.kwargs["context"]["total"] == 1
        assert len(ctx.kwargs["context"]["campaigns"]) == 1
        assert ctx.kwargs["context"]["statuses"] == CAMPAIGN_STATUSES

    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_with_search_and_status(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request(query_params={})
        mock_mc.get_campaigns = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_tpl.TemplateResponse.return_value = "rendered"

        await email_campaigns_list(
            request=req,
            page=2,
            search="test",
            status="draft",
            auth_result=user,
        )

        mock_mc.get_campaigns.assert_awaited_once_with(
            page=2,
            page_size=20,
            status="draft",
            search="test",
        )

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaigns_list(
            request=_make_request(),
            page=1,
            search=None,
            status=None,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignNew:
    """Tests for email_campaign_new handler."""

    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request()
        mock_mc.get_templates = AsyncMock(return_value={"items": [{"id": 1}]})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": [{"id": 10}]})
        mock_mc.get_providers = AsyncMock(return_value=["brevo"])
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_campaign_new(request=req, auth_result=user)

        assert result == "rendered"
        mock_mc.get_templates.assert_awaited_once_with(page=1, page_size=100, status="active")
        mock_mc.get_contact_groups.assert_awaited_once_with(page=1, page_size=100)
        mock_mc.get_providers.assert_awaited_once()
        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["campaign"] is None
        assert ctx["is_edit"] is False
        assert ctx["email_templates"] == [{"id": 1}]
        assert ctx["contact_groups"] == [{"id": 10}]
        assert ctx["email_providers"] == ["brevo"]

    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_shows_the_error_of_a_failed_creation(self, mock_mc, mock_tpl):
        req = _make_request(query_params={"error": "Failed to create campaign"})
        mock_mc.get_templates = AsyncMock(return_value={"items": []})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": []})
        mock_mc.get_providers = AsyncMock(return_value=[])
        mock_tpl.TemplateResponse.return_value = "rendered"

        await email_campaign_new(request=req, auth_result=_make_user())

        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["error"] == "Failed to create campaign"

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_new(request=_make_request(), auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignCreate:
    """Tests for email_campaign_create handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_campaign = AsyncMock(return_value={"id": 42})

        result = await email_campaign_create(
            request=req,
            name="  My Campaign  ",
            description="  desc  ",
            template_id=1,
            group_id=2,
            provider="brevo",
            from_name="Test",
            from_email="test@test.com",
            reply_to="reply@test.com",
            scheduled_at="2024-02-01T10:00:00",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "42" in result.headers["location"]
        assert "success" in result.headers["location"]
        call_data = mock_mc.create_campaign.call_args[0][0]
        assert call_data["name"] == "My Campaign"
        assert call_data["description"] == "desc"
        assert call_data["scheduled_at"] == "2024-02-01T10:00:00"

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success_without_scheduled_at(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_campaign = AsyncMock(return_value={"id": 42})

        await email_campaign_create(
            request=req,
            name="C",
            description="",
            template_id=1,
            group_id=2,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=user,
        )

        call_data = mock_mc.create_campaign.call_args[0][0]
        assert "scheduled_at" not in call_data
        assert call_data["provider"] is None
        assert call_data["from_name"] is None
        assert call_data["description"] is None

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_create_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_campaign = AsyncMock(return_value=None)

        result = await email_campaign_create(
            request=req,
            name="C",
            description="",
            template_id=1,
            group_id=2,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_create(
            request=_make_request(),
            name="C",
            description="",
            template_id=1,
            group_id=2,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignsBulkDelete:
    """Tests for email_campaigns_bulk_delete handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success_deletes_campaigns(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)

        mock_mc.get_campaign = AsyncMock(
            side_effect=[
                {"id": 1, "status": "draft"},
                {"id": 2, "status": "draft"},
            ]
        )
        mock_mc.delete_campaign = AsyncMock(return_value=True)

        result = await email_campaigns_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Deleted+2" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_skips_sending_campaigns(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)

        mock_mc.get_campaign = AsyncMock(
            side_effect=[
                {"id": 1, "status": "sending"},
                {"id": 2, "status": "draft"},
            ]
        )
        mock_mc.delete_campaign = AsyncMock(return_value=True)

        result = await email_campaigns_bulk_delete(request=req, auth_result=user)

        assert "Skipped+1" in result.headers["location"]
        assert "Deleted+1" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_no_campaign_ids(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        req.form = AsyncMock(return_value=form_mock)

        result = await email_campaigns_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "No+campaigns+selected" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_invalid_campaign_ids(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["abc", "xyz"]
        req.form = AsyncMock(return_value=form_mock)

        result = await email_campaigns_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Invalid+campaign+IDs" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_empty_strings_in_ids(self, mock_mc):
        """Campaign IDs that are empty strings result in no valid IDs."""
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["", ""]
        req.form = AsyncMock(return_value=form_mock)

        result = await email_campaigns_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "No+campaigns+selected" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found_skipped(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1"]
        req.form = AsyncMock(return_value=form_mock)
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaigns_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Deleted+0" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_delete_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1"]
        req.form = AsyncMock(return_value=form_mock)
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.delete_campaign = AsyncMock(return_value=False)

        result = await email_campaigns_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Deleted+0" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaigns_bulk_delete(request=_make_request(), auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignDetail:
    """Tests for email_campaign_detail handler."""

    @patch("internal.routes.email_campaigns.settings")
    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc, mock_tpl, mock_settings):
        user = _make_user()
        req = _make_request(query_params={"success": "ok", "error": None})
        mock_settings.mailler_default_provider = "brevo"
        mock_mc.get_campaign = AsyncMock(
            return_value={
                "id": 1,
                "name": "Test",
                "status": "draft",
                "created_at": "2024-01-15T10:00:00Z",
                "stats": {
                    "pending_count": 5,
                    "sent_count": 10,
                },
            }
        )
        mock_mc.get_campaign_sends = AsyncMock(
            return_value={
                "items": [{"created_at": "2024-01-15T10:00:00Z"}],
            }
        )
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_campaign_detail(request=req, campaign_id=1, auth_result=user)

        assert result == "rendered"
        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        # Stats should be flattened into campaign dict
        assert ctx["campaign"]["pending_count"] == 5
        assert ctx["campaign"]["sent_count"] == 10
        assert ctx["default_provider"] == "brevo"
        assert ctx["send_statuses"] == SEND_STATUSES

    @patch("internal.routes.email_campaigns.settings")
    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_without_stats_dict(self, mock_mc, mock_tpl, mock_settings):
        """When stats is not a dict, it should not be flattened."""
        user = _make_user()
        req = _make_request(query_params={})
        mock_settings.mailler_default_provider = "brevo"
        mock_mc.get_campaign = AsyncMock(
            return_value={
                "id": 1,
                "name": "Test",
                "status": "draft",
                "created_at": "2024-01-15T10:00:00Z",
            }
        )
        mock_mc.get_campaign_sends = AsyncMock(return_value={"items": []})
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_campaign_detail(request=req, campaign_id=1, auth_result=user)
        assert result == "rendered"

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_detail(request=req, campaign_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_detail(
            request=_make_request(),
            campaign_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignEdit:
    """Tests for email_campaign_edit handler."""

    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(
            return_value={
                "id": 1,
                "name": "Test",
                "status": "draft",
                "created_at": "2024-01-15T10:00:00Z",
            }
        )
        mock_mc.get_templates = AsyncMock(return_value={"items": []})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": []})
        mock_mc.get_providers = AsyncMock(return_value=[])
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_campaign_edit(request=req, campaign_id=1, auth_result=user)

        assert result == "rendered"
        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["is_edit"] is True
        assert ctx["campaign"]["id"] == 1

    @patch("internal.routes.email_campaigns.templates")
    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_shows_the_error_of_a_failed_update(self, mock_mc, mock_tpl):
        req = _make_request(query_params={"error": "Failed to update campaign"})
        mock_mc.get_campaign = AsyncMock(
            return_value={
                "id": 1,
                "name": "Test",
                "status": "draft",
                "created_at": "2024-01-15T10:00:00Z",
            }
        )
        mock_mc.get_templates = AsyncMock(return_value={"items": []})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": []})
        mock_mc.get_providers = AsyncMock(return_value=[])
        mock_tpl.TemplateResponse.return_value = "rendered"

        await email_campaign_edit(request=req, campaign_id=1, auth_result=_make_user())

        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["error"] == "Failed to update campaign"

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_edit(request=req, campaign_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_blocks_sending_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "sending"})

        result = await email_campaign_edit(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Cannot+edit" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_blocks_completed_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "completed"})

        result = await email_campaign_edit(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Cannot+edit" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_edit(
            request=_make_request(),
            campaign_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignUpdate:
    """Tests for email_campaign_update handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.update_campaign = AsyncMock(return_value={"id": 1})

        result = await email_campaign_update(
            request=req,
            campaign_id=1,
            name="  Updated  ",
            description="  desc  ",
            template_id=2,
            group_id=3,
            provider="brevo",
            from_name="Me",
            from_email="me@test.com",
            reply_to="reply@test.com",
            scheduled_at="2024-03-01T10:00:00",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        call_args = mock_mc.update_campaign.call_args
        assert call_args[0][0] == 1
        assert call_args[0][1]["name"] == "Updated"
        assert call_args[0][1]["scheduled_at"] == "2024-03-01T10:00:00"

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success_empty_optional_fields(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.update_campaign = AsyncMock(return_value={"id": 1})

        await email_campaign_update(
            request=req,
            campaign_id=1,
            name="Test",
            description="",
            template_id=1,
            group_id=1,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=user,
        )

        call_data = mock_mc.update_campaign.call_args[0][1]
        assert call_data["description"] is None
        assert call_data["provider"] is None
        assert call_data["scheduled_at"] is None

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_update(
            request=req,
            campaign_id=999,
            name="C",
            description="",
            template_id=1,
            group_id=1,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_blocks_sending_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "sending"})

        result = await email_campaign_update(
            request=req,
            campaign_id=1,
            name="C",
            description="",
            template_id=1,
            group_id=1,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "Cannot+edit" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_blocks_completed_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "completed"})

        result = await email_campaign_update(
            request=req,
            campaign_id=1,
            name="C",
            description="",
            template_id=1,
            group_id=1,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "Cannot+edit" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_update_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.update_campaign = AsyncMock(return_value=None)

        result = await email_campaign_update(
            request=req,
            campaign_id=1,
            name="C",
            description="",
            template_id=1,
            group_id=1,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+update" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_update(
            request=_make_request(),
            campaign_id=1,
            name="C",
            description="",
            template_id=1,
            group_id=1,
            provider="",
            from_name="",
            from_email="",
            reply_to="",
            scheduled_at="",
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignSend:
    """Tests for email_campaign_send handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.send_campaign = AsyncMock(return_value={"total_recipients": 42})

        result = await email_campaign_send(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        assert "sending+started" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success_scheduled_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "scheduled"})
        mock_mc.send_campaign = AsyncMock(return_value={"total_recipients": 5})

        result = await email_campaign_send(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_send(request=req, campaign_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_wrong_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "sending"})

        result = await email_campaign_send(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "cannot+be+sent" in result.headers["location"].lower()

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_mailler_api_error(self, mock_mc):
        """Test the MaillerAPIError catch path."""
        from internal.services.mailler_client import MaillerAPIError as RealError

        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})

        error = RealError("No recipients found", status_code=400)
        mock_mc.send_campaign = AsyncMock(side_effect=error)

        result = await email_campaign_send(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "No+recipients+found" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_send(
            request=_make_request(),
            campaign_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignSendMaillerAPIError:
    """Separate test class to test MaillerAPIError path without class mock conflicts."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_catches_mailler_api_error(self, mock_mc):
        from internal.services.mailler_client import MaillerAPIError

        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.send_campaign = AsyncMock(
            side_effect=MaillerAPIError("No recipients found", status_code=400),
        )

        result = await email_campaign_send(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "No+recipients+found" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_catches_mailler_api_error_spaces_replaced(self, mock_mc):
        """Verify spaces in error message are replaced with +."""
        from internal.services.mailler_client import MaillerAPIError

        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.send_campaign = AsyncMock(
            side_effect=MaillerAPIError("Group has no active contacts", status_code=400),
        )

        result = await email_campaign_send(request=req, campaign_id=1, auth_result=user)

        assert "Group+has+no+active+contacts" in result.headers["location"]


@pytest.mark.asyncio
class TestEmailCampaignPause:
    """Tests for email_campaign_pause handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "sending"})
        mock_mc.pause_campaign = AsyncMock(return_value={"id": 1})

        result = await email_campaign_pause(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "paused" in result.headers["location"].lower()

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_pause(request=req, campaign_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_wrong_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})

        result = await email_campaign_pause(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+currently+sending" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_pause_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "sending"})
        mock_mc.pause_campaign = AsyncMock(return_value=None)

        result = await email_campaign_pause(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+pause" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_pause(
            request=_make_request(),
            campaign_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignResume:
    """Tests for email_campaign_resume handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "paused"})
        mock_mc.resume_campaign = AsyncMock(return_value={"id": 1})

        result = await email_campaign_resume(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "resumed" in result.headers["location"].lower()

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_resume(request=req, campaign_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_wrong_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})

        result = await email_campaign_resume(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+paused" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_resume_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "paused"})
        mock_mc.resume_campaign = AsyncMock(return_value=None)

        result = await email_campaign_resume(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+resume" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_resume(
            request=_make_request(),
            campaign_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignDelete:
    """Tests for email_campaign_delete handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.delete_campaign = AsyncMock(return_value=True)

        result = await email_campaign_delete(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "deleted+successfully" in result.headers["location"].lower()

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_delete(request=req, campaign_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_blocks_sending_status(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "sending"})

        result = await email_campaign_delete(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "while+sending" in result.headers["location"]

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_delete_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value={"id": 1, "status": "draft"})
        mock_mc.delete_campaign = AsyncMock(return_value=False)

        result = await email_campaign_delete(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+delete" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_delete(
            request=_make_request(),
            campaign_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailCampaignStats:
    """Tests for email_campaign_stats handler."""

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(
            return_value={
                "id": 1,
                "status": "sending",
                "stats": {
                    "total_recipients": 100,
                    "sent_count": 50,
                    "delivered_count": 45,
                    "opened_count": 20,
                    "clicked_count": 10,
                    "bounced_count": 3,
                    "complained_count": 1,
                    "failed_count": 2,
                    "progress_percent": 50,
                    "open_rate": 44.4,
                    "click_rate": 22.2,
                    "bounce_rate": 6.7,
                    "complaint_rate": 2.2,
                },
            }
        )

        result = await email_campaign_stats(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, JSONResponse)
        # Decode body
        body = result.body.decode()
        import json

        data = json.loads(body)
        assert data["id"] == 1
        assert data["status"] == "sending"
        assert data["total_recipients"] == 100
        assert data["sent_count"] == 50
        assert data["open_rate"] == 44.4

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_campaign_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(return_value=None)

        result = await email_campaign_stats(request=req, campaign_id=999, auth_result=user)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 404

    @patch("internal.routes.email_campaigns.mailler_client")
    async def test_empty_stats(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_campaign = AsyncMock(
            return_value={
                "id": 1,
                "status": "draft",
            }
        )

        result = await email_campaign_stats(request=req, campaign_id=1, auth_result=user)

        assert isinstance(result, JSONResponse)
        import json

        data = json.loads(result.body.decode())
        assert data["total_recipients"] == 0
        assert data["sent_count"] == 0

    async def test_returns_401_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_campaign_stats(
            request=_make_request(),
            campaign_id=1,
            auth_result=redirect,
        )

        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        import json

        data = json.loads(result.body.decode())
        assert data["error"] == "Unauthorized"


class TestEmailCampaignProviderLabel:
    """The detail page says which provider a campaign uses, without assuming one."""

    @staticmethod
    def _render(provider, default_provider):
        from internal.routes.email_campaigns import templates

        campaign = {
            "id": 1,
            "name": "Spring",
            "status": "draft",
            "provider": provider,
            "created_at": datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            **{
                f"{name}_count": 0
                for name in ("sent", "delivered", "opened", "clicked", "bounced", "complained")
            },
            "failed_count": 0,
        }
        return templates.get_template("admin/email_campaigns/detail.html").render(
            request=MagicMock(),
            user=_make_user(),
            active_section="email_campaigns",
            campaign=campaign,
            recent_sends=[],
            status_counts={},
            send_statuses=SEND_STATUSES,
            default_provider=default_provider,
            success=None,
            error=None,
        )

    def test_the_provider_of_the_campaign(self):
        assert 'badge-info">Ses<' in self._render("ses", "other")

    def test_the_configured_default_provider(self):
        assert 'badge-info">Other<' in self._render(None, "other")

    def test_without_any_provider_the_one_of_the_mailler_client_applies(self):
        assert 'badge-info">Client default<' in self._render(None, "")
