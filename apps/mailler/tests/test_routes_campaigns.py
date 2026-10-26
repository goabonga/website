# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for email campaign CRUD routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient


def _make_db_list_response(items=None, total=0):
    count_result = MagicMock()
    count_result.scalar.return_value = total
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items or []
    return [count_result, list_result]


def _make_campaign_mock(**overrides):
    now = datetime.now(UTC)
    template_mock = MagicMock()
    template_mock.id = overrides.get("template_id", 1)
    template_mock.name = "Template"
    template_mock.subject_template = "Subject"

    group_mock = MagicMock()
    group_mock.id = overrides.get("group_id", 1)
    group_mock.name = "Group"
    group_mock.member_count = 0
    group_mock.members = []

    c = MagicMock()
    c.id = overrides.get("id", 1)
    c.client_id = overrides.get("client_id", "test-client-id")
    c.name = overrides.get("name", "Campaign")
    c.description = overrides.get("description")
    c.template_id = overrides.get("template_id", 1)
    c.group_id = overrides.get("group_id", 1)
    c.template = overrides.get("template", template_mock)
    c.group = overrides.get("group", group_mock)
    c.status = overrides.get("status", "draft")
    c.scheduled_at = overrides.get("scheduled_at")
    c.started_at = overrides.get("started_at")
    c.completed_at = overrides.get("completed_at")
    c.from_name = overrides.get("from_name")
    c.from_email = overrides.get("from_email")
    c.reply_to = overrides.get("reply_to")
    c.provider = overrides.get("provider", "brevo")
    c.subject_override = overrides.get("subject_override")
    c.task_id = overrides.get("task_id")
    c.metadata_ = overrides.get("metadata_", {})
    c.total_recipients = overrides.get("total_recipients", 0)
    c.sent_count = overrides.get("sent_count", 0)
    c.delivered_count = overrides.get("delivered_count", 0)
    c.opened_count = overrides.get("opened_count", 0)
    c.clicked_count = overrides.get("clicked_count", 0)
    c.bounced_count = overrides.get("bounced_count", 0)
    c.complained_count = overrides.get("complained_count", 0)
    c.failed_count = overrides.get("failed_count", 0)
    c.progress_percent = overrides.get("progress_percent", 0.0)
    c.open_rate = overrides.get("open_rate", 0.0)
    c.click_rate = overrides.get("click_rate", 0.0)
    c.bounce_rate = overrides.get("bounce_rate", 0.0)
    c.complaint_rate = overrides.get("complaint_rate", 0.0)
    c.created_at = overrides.get("created_at", now)
    c.updated_at = overrides.get("updated_at", now)
    return c


def _make_send_mock(**overrides):
    now = datetime.now(UTC)
    s = MagicMock()
    s.id = overrides.get("id", uuid4())
    s.recipient_email = overrides.get("recipient_email", "r@t.com")
    s.recipient_name = overrides.get("recipient_name", "R")
    s.status = overrides.get("status", "sent")
    s.sent_at = overrides.get("sent_at", now)
    s.delivered_at = overrides.get("delivered_at")
    s.opened_at = overrides.get("opened_at")
    s.error_message = overrides.get("error_message")
    s.created_at = overrides.get("created_at", now)
    return s


# --------------------------------------------------------------------------
# GET /campaigns
# --------------------------------------------------------------------------


class TestListCampaigns:
    async def test_list_empty(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_with_items(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock()
        mock_db_session.execute = AsyncMock(
            side_effect=_make_db_list_response(items=[campaign], total=1)
        )
        response = await auth_client.get("/api/v1/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Campaign"
        assert data["items"][0]["template"]["id"] == 1
        assert data["items"][0]["group"]["id"] == 1

    async def test_list_with_status_filter(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/campaigns?status=draft")
        assert response.status_code == 200

    async def test_list_with_search(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/campaigns?search=test")
        assert response.status_code == 200

    async def test_list_no_template_no_group(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(template=None, group=None)
        mock_db_session.execute = AsyncMock(
            side_effect=_make_db_list_response(items=[campaign], total=1)
        )
        response = await auth_client.get("/api/v1/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["template"] is None
        assert data["items"][0]["group"] is None


# --------------------------------------------------------------------------
# POST /campaigns
# --------------------------------------------------------------------------


class TestCreateCampaign:
    async def test_create_success(self, admin_client: AsyncClient, mock_db_session):
        template_mock = MagicMock(id=1, client_id="admin-client-id")
        group_mock = MagicMock(id=1, client_id="admin-client-id")
        mock_db_session.get = AsyncMock(side_effect=[template_mock, group_mock])

        campaign_mock = _make_campaign_mock()
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = campaign_mock
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.post(
            "/api/v1/campaigns",
            json={"name": "Campaign", "template_id": 1, "group_id": 1, "provider": "brevo"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Campaign"
        assert data["status"] == "draft"

    async def test_create_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.post(
            "/api/v1/campaigns",
            json={"name": "C", "template_id": 999, "provider": "brevo"},
        )
        assert response.status_code == 404
        assert "Template" in response.json()["detail"]

    async def test_create_group_not_found(self, admin_client: AsyncClient, mock_db_session):
        template_mock = MagicMock(id=1, client_id="admin-client-id")
        mock_db_session.get = AsyncMock(side_effect=[template_mock, None])
        response = await admin_client.post(
            "/api/v1/campaigns",
            json={"name": "C", "template_id": 1, "group_id": 999, "provider": "brevo"},
        )
        assert response.status_code == 404
        assert "group" in response.json()["detail"].lower()

    async def test_create_with_scheduled_at(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(
            return_value=None
        )  # No template/group validation needed if not set
        campaign_mock = _make_campaign_mock(status="scheduled")
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = campaign_mock
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.post(
            "/api/v1/campaigns",
            json={
                "name": "C",
                "provider": "brevo",
                "scheduled_at": "2030-01-01T00:00:00Z",
            },
        )
        assert response.status_code == 201

    async def test_create_no_template_no_group(self, admin_client: AsyncClient, mock_db_session):
        """No validation called if template_id and group_id not provided."""
        campaign_mock = _make_campaign_mock(
            template=None, group=None, template_id=None, group_id=None
        )
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = campaign_mock
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.post(
            "/api/v1/campaigns",
            json={"name": "C", "provider": "brevo"},
        )
        assert response.status_code == 201

    async def test_create_not_found_after_creation(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Cover line 284: get_campaign_with_relations returns None after create."""
        # No template_id or group_id so no validation via db.get
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.post(
            "/api/v1/campaigns",
            json={"name": "Ghost", "provider": "brevo"},
        )
        assert response.status_code == 404
        assert "after creation" in response.json()["detail"]


# --------------------------------------------------------------------------
# GET /campaigns/{id}
# --------------------------------------------------------------------------


class TestGetCampaign:
    async def test_get_found(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = campaign
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get("/api/v1/campaigns/1")
        assert response.status_code == 200
        assert response.json()["name"] == "Campaign"

    async def test_get_not_found(self, auth_client: AsyncClient, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await auth_client.get("/api/v1/campaigns/999")
        assert response.status_code == 404

    async def test_get_no_template_no_group(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(template=None, group=None)
        result = MagicMock()
        result.scalar_one_or_none.return_value = campaign
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get("/api/v1/campaigns/1")
        assert response.status_code == 200
        data = response.json()
        assert data["template"] is None
        assert data["group"] is None


# --------------------------------------------------------------------------
# PUT /campaigns/{id}
# --------------------------------------------------------------------------


class TestUpdateCampaign:
    async def test_update_success(self, admin_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(
            side_effect=[campaign, MagicMock(id=2, client_id="test-client-id")]
        )  # campaign, then template

        reloaded = _make_campaign_mock(name="Updated", template_id=2)
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.put(
            "/api/v1/campaigns/1",
            json={"name": "Updated", "template_id": 2},
        )
        assert response.status_code == 200

    async def test_update_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.put("/api/v1/campaigns/999", json={"name": "X"})
        assert response.status_code == 404

    async def test_update_wrong_status(self, admin_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="sending")
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await admin_client.put("/api/v1/campaigns/1", json={"name": "X"})
        assert response.status_code == 400
        assert "Cannot edit" in response.json()["detail"]

    async def test_update_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(side_effect=[campaign, None])
        response = await admin_client.put("/api/v1/campaigns/1", json={"template_id": 999})
        assert response.status_code == 404

    async def test_update_group_not_found(self, admin_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(side_effect=[campaign, None])
        response = await admin_client.put("/api/v1/campaigns/1", json={"group_id": 999})
        assert response.status_code == 404

    async def test_update_all_fields(self, admin_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(return_value=campaign)

        reloaded = _make_campaign_mock()
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.put(
            "/api/v1/campaigns/1",
            json={
                "name": "N",
                "description": "D",
                "from_name": "FN",
                "from_email": "f@t.com",
                "reply_to": "r@t.com",
                "provider": "ses",
                "subject_override": "S",
                "scheduled_at": "2030-01-01T00:00:00Z",
                "metadata": {"k": "v"},
            },
        )
        assert response.status_code == 200

    async def test_update_with_valid_group_id(self, admin_client: AsyncClient, mock_db_session):
        """Cover line 373: successful group_id assignment during update."""
        campaign = _make_campaign_mock(status="draft")
        group_mock = MagicMock(id=5, client_id="test-client-id")
        # First get returns campaign, second get returns the group
        mock_db_session.get = AsyncMock(side_effect=[campaign, group_mock])

        reloaded = _make_campaign_mock(group_id=5)
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.put(
            "/api/v1/campaigns/1",
            json={"group_id": 5},
        )
        assert response.status_code == 200

    async def test_update_scheduled_at_on_already_scheduled(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Cover lines 392->394: update scheduled_at on a campaign already in scheduled status.

        When campaign.status is 'scheduled' (not 'draft'), the inner branch
        `if campaign.status == CampaignStatus.DRAFT.value` is False,
        so it should NOT change the status.
        """
        campaign = _make_campaign_mock(status="scheduled")
        mock_db_session.get = AsyncMock(return_value=campaign)

        reloaded = _make_campaign_mock(status="scheduled")
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.put(
            "/api/v1/campaigns/1",
            json={"scheduled_at": "2031-06-01T00:00:00Z"},
        )
        assert response.status_code == 200

    async def test_update_not_found_after_update(self, admin_client: AsyncClient, mock_db_session):
        """Cover line 408: get_campaign_with_relations returns None after update."""
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(return_value=campaign)

        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.put(
            "/api/v1/campaigns/1",
            json={"name": "Updated"},
        )
        assert response.status_code == 404
        assert "after update" in response.json()["detail"]


# --------------------------------------------------------------------------
# DELETE /campaigns/{id}
# --------------------------------------------------------------------------


class TestDeleteCampaign:
    async def test_delete_success(self, admin_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await admin_client.delete("/api/v1/campaigns/1")
        assert response.status_code == 204

    async def test_delete_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.delete("/api/v1/campaigns/999")
        assert response.status_code == 404

    async def test_delete_sending_blocked(self, admin_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="sending")
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await admin_client.delete("/api/v1/campaigns/1")
        assert response.status_code == 400
        assert "sending" in response.json()["detail"].lower()


# --------------------------------------------------------------------------
# POST /campaigns/{id}/schedule
# --------------------------------------------------------------------------


class TestScheduleCampaign:
    async def test_schedule_success(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft", template_id=1, group_id=1)
        mock_db_session.get = AsyncMock(return_value=campaign)

        response = await auth_client.post(
            "/api/v1/campaigns/1/schedule",
            json={"scheduled_at": "2030-01-01T00:00:00Z"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scheduled"
        assert data["message"] == "Campaign scheduled successfully"

    async def test_schedule_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.post(
            "/api/v1/campaigns/999/schedule",
            json={"scheduled_at": "2030-01-01T00:00:00Z"},
        )
        assert response.status_code == 404

    async def test_schedule_wrong_status(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="sending")
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post(
            "/api/v1/campaigns/1/schedule",
            json={"scheduled_at": "2030-01-01T00:00:00Z"},
        )
        assert response.status_code == 400

    async def test_schedule_no_template(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft", template_id=None)
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post(
            "/api/v1/campaigns/1/schedule",
            json={"scheduled_at": "2030-01-01T00:00:00Z"},
        )
        assert response.status_code == 400

    async def test_schedule_no_group(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft", template_id=1, group_id=None)
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post(
            "/api/v1/campaigns/1/schedule",
            json={"scheduled_at": "2030-01-01T00:00:00Z"},
        )
        assert response.status_code == 400


# --------------------------------------------------------------------------
# POST /campaigns/{id}/send
# --------------------------------------------------------------------------


class TestStartCampaign:
    async def test_send_success(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft", template_id=1, group_id=1)
        mock_db_session.get = AsyncMock(return_value=campaign)

        count_result = MagicMock()
        count_result.scalar.return_value = 50
        mock_db_session.execute = AsyncMock(return_value=count_result)

        with patch("mailler.routes.campaigns.send_campaign_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-123")
            response = await auth_client.post("/api/v1/campaigns/1/send")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sending"
        assert data["total_recipients"] == 50
        assert data["task_id"] == "task-123"

    async def test_send_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.post("/api/v1/campaigns/999/send")
        assert response.status_code == 404

    async def test_send_wrong_status(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="completed")
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post("/api/v1/campaigns/1/send")
        assert response.status_code == 400

    async def test_send_no_template(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft", template_id=None)
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post("/api/v1/campaigns/1/send")
        assert response.status_code == 400

    async def test_send_no_group(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft", template_id=1, group_id=None)
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post("/api/v1/campaigns/1/send")
        assert response.status_code == 400

    async def test_send_no_active_contacts(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft", template_id=1, group_id=1)
        mock_db_session.get = AsyncMock(return_value=campaign)
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=count_result)

        response = await auth_client.post("/api/v1/campaigns/1/send")
        assert response.status_code == 400
        assert "No active contacts" in response.json()["detail"]


# --------------------------------------------------------------------------
# POST /campaigns/{id}/pause
# --------------------------------------------------------------------------


class TestPauseCampaign:
    async def test_pause_success(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="sending", sent_count=25)
        mock_db_session.get = AsyncMock(return_value=campaign)

        response = await auth_client.post("/api/v1/campaigns/1/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"
        assert data["sent_count"] == 25

    async def test_pause_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.post("/api/v1/campaigns/999/pause")
        assert response.status_code == 404

    async def test_pause_wrong_status(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post("/api/v1/campaigns/1/pause")
        assert response.status_code == 400


# --------------------------------------------------------------------------
# POST /campaigns/{id}/resume
# --------------------------------------------------------------------------


class TestResumeCampaign:
    async def test_resume_success(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="paused", total_recipients=100)
        mock_db_session.get = AsyncMock(return_value=campaign)

        with patch("mailler.routes.campaigns.send_campaign_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-456")
            response = await auth_client.post("/api/v1/campaigns/1/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sending"
        assert data["task_id"] == "task-456"

    async def test_resume_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.post("/api/v1/campaigns/999/resume")
        assert response.status_code == 404

    async def test_resume_wrong_status(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(status="draft")
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.post("/api/v1/campaigns/1/resume")
        assert response.status_code == 400


# --------------------------------------------------------------------------
# GET /campaigns/{id}/preview
# --------------------------------------------------------------------------


class TestPreviewCampaign:
    async def test_preview_success(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(template_id=1, group_id=1)
        template = MagicMock()
        template.html_compiled = "<p>Hello</p>"
        template.subject_template = "Subject"
        template.plain_text = "Hello"

        mock_db_session.get = AsyncMock(side_effect=[campaign, template])

        count_result = MagicMock()
        count_result.scalar.return_value = 10
        mock_db_session.execute = AsyncMock(return_value=count_result)

        response = await auth_client.get("/api/v1/campaigns/1/preview")
        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "Subject"
        assert data["html"] == "<p>Hello</p>"
        assert data["recipient_count"] == 10

    async def test_preview_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.get("/api/v1/campaigns/999/preview")
        assert response.status_code == 404

    async def test_preview_no_template_id(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(template_id=None)
        mock_db_session.get = AsyncMock(return_value=campaign)
        response = await auth_client.get("/api/v1/campaigns/1/preview")
        assert response.status_code == 400

    async def test_preview_template_not_found(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(template_id=1)
        mock_db_session.get = AsyncMock(side_effect=[campaign, None])
        response = await auth_client.get("/api/v1/campaigns/1/preview")
        assert response.status_code == 404

    async def test_preview_no_group(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(template_id=1, group_id=None)
        template = MagicMock()
        template.html_compiled = "<p>X</p>"
        template.subject_template = "S"
        template.plain_text = None
        mock_db_session.get = AsyncMock(side_effect=[campaign, template])

        response = await auth_client.get("/api/v1/campaigns/1/preview")
        assert response.status_code == 200
        assert response.json()["recipient_count"] == 0

    async def test_preview_with_subject_override(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock(template_id=1, group_id=None, subject_override="Override")
        template = MagicMock()
        template.html_compiled = ""
        template.subject_template = "Original"
        template.plain_text = None
        mock_db_session.get = AsyncMock(side_effect=[campaign, template])

        response = await auth_client.get("/api/v1/campaigns/1/preview")
        assert response.status_code == 200
        assert response.json()["subject"] == "Override"


# --------------------------------------------------------------------------
# GET /campaigns/{id}/sends
# --------------------------------------------------------------------------


class TestListCampaignSends:
    async def test_list_sends_success(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock()
        send = _make_send_mock()

        mock_db_session.get = AsyncMock(return_value=campaign)
        mock_db_session.execute = AsyncMock(
            side_effect=_make_db_list_response(items=[send], total=1)
        )

        response = await auth_client.get("/api/v1/campaigns/1/sends")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1

    async def test_list_sends_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.get("/api/v1/campaigns/999/sends")
        assert response.status_code == 404

    async def test_list_sends_with_status_filter(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock()
        mock_db_session.get = AsyncMock(return_value=campaign)
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/campaigns/1/sends?status=sent")
        assert response.status_code == 200

    async def test_list_sends_empty(self, auth_client: AsyncClient, mock_db_session):
        campaign = _make_campaign_mock()
        mock_db_session.get = AsyncMock(return_value=campaign)
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/campaigns/1/sends")
        assert response.status_code == 200
        assert response.json()["items"] == []


# --------------------------------------------------------------------------
# Isolation between clients
# --------------------------------------------------------------------------


def _params(mock_db_session, call=0):
    return mock_db_session.execute.await_args_list[call].args[0].compile().params


class TestCampaignsBelongToTheirClient:
    async def test_list_is_restricted_to_the_client(self, auth_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        assert (await auth_client.get("/api/v1/campaigns")).status_code == 200
        assert _params(mock_db_session, 0)["client_id_1"] == "test-client-id"
        assert _params(mock_db_session, 1)["client_id_1"] == "test-client-id"

    async def test_list_of_another_client_is_forbidden(self, auth_client):
        assert (await auth_client.get("/api/v1/campaigns?client_id=other")).status_code == 403

    async def test_admin_lists_every_client(self, admin_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        await admin_client.get("/api/v1/campaigns")
        assert "client_id_1" not in _params(mock_db_session, 1)

    async def test_created_campaign_is_owned_by_the_caller(self, writer_client, mock_db_session):
        mock_db_session.get = AsyncMock(
            side_effect=[
                MagicMock(id=1, client_id="test-client-id"),
                MagicMock(id=1, client_id="test-client-id"),
            ]
        )
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = _make_campaign_mock()
        mock_db_session.execute = AsyncMock(return_value=reload_result)
        response = await writer_client.post(
            "/api/v1/campaigns", json={"name": "C", "template_id": 1, "group_id": 1}
        )
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "test-client-id"
        assert response.json()["client_id"] == "test-client-id"

    async def test_template_or_group_of_another_client_is_not_found(
        self, writer_client, mock_db_session
    ):
        mock_db_session.get = AsyncMock(return_value=MagicMock(id=1, client_id="other"))
        response = await writer_client.post(
            "/api/v1/campaigns", json={"name": "C", "template_id": 1}
        )
        assert response.status_code == 404
        assert "Template" in response.json()["detail"]

        mock_db_session.get = AsyncMock(
            side_effect=[MagicMock(id=1, client_id="test-client-id"), MagicMock(client_id="other")]
        )
        response = await writer_client.post(
            "/api/v1/campaigns", json={"name": "C", "template_id": 1, "group_id": 2}
        )
        assert response.status_code == 404
        assert "group" in response.json()["detail"].lower()
        mock_db_session.add.assert_not_called()

    async def test_regular_caller_cannot_create_for_another_client(
        self, writer_client, mock_db_session
    ):
        response = await writer_client.post("/api/v1/campaigns?client_id=other", json={"name": "C"})
        assert response.status_code == 403
        mock_db_session.add.assert_not_called()

    async def test_admin_creates_for_another_client(self, admin_client, mock_db_session):
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = _make_campaign_mock(client_id="other")
        mock_db_session.execute = AsyncMock(return_value=reload_result)
        response = await admin_client.post("/api/v1/campaigns?client_id=other", json={"name": "C"})
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "other"

    async def test_campaign_of_another_client_is_not_found_everywhere(
        self, writer_client, mock_db_session
    ):
        foreign = _make_campaign_mock(client_id="other")
        mock_db_session.get = AsyncMock(return_value=foreign)
        result = MagicMock()
        result.scalar_one_or_none.return_value = foreign
        mock_db_session.execute = AsyncMock(return_value=result)
        for method, path, body in (
            ("GET", "/api/v1/campaigns/1", None),
            ("PUT", "/api/v1/campaigns/1", {"name": "Hijacked"}),
            ("DELETE", "/api/v1/campaigns/1", None),
            ("POST", "/api/v1/campaigns/1/schedule", {"scheduled_at": "2030-01-01T10:00:00Z"}),
            ("POST", "/api/v1/campaigns/1/send", None),
            ("POST", "/api/v1/campaigns/1/pause", None),
            ("POST", "/api/v1/campaigns/1/resume", None),
            ("GET", "/api/v1/campaigns/1/preview", None),
            ("GET", "/api/v1/campaigns/1/sends", None),
        ):
            response = await writer_client.request(method, path, json=body)
            assert response.status_code == 404, (method, path, response.status_code)
        mock_db_session.delete.assert_not_called()
        assert foreign.name != "Hijacked"

    async def test_admin_reads_any_client(self, admin_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = _make_campaign_mock(client_id="other")
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await admin_client.get("/api/v1/campaigns/1")
        assert response.status_code == 200
        assert response.json()["client_id"] == "other"
