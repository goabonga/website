# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for inbound email routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from mailler.main import app
from mailler.routes.inbound import router as inbound_router

# ---------------------------------------------------------------------------
# The inbound router is only registered when settings.inbound_enabled is True.
# Since the test app is created with inbound_enabled=False (the default), we
# register the router here for the duration of these tests.
# ---------------------------------------------------------------------------

_INBOUND_PREFIX = "/api/v1"
_inbound_registered = False


@pytest.fixture(autouse=True, scope="module")
def _register_inbound_router():
    """Register the inbound router on the test app if not already present."""
    global _inbound_registered
    if not _inbound_registered:
        app.include_router(inbound_router, prefix=_INBOUND_PREFIX)
        _inbound_registered = True
    yield


def _make_db_list_response(items=None, total=0):
    """Create mock DB response for paginated list queries (count + list)."""
    count_result = MagicMock()
    count_result.scalar.return_value = total

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items or []

    return [count_result, list_result]


def _make_inbound_email_mock(**overrides):
    """Create a mock InboundEmail with default values."""
    now = datetime.now(UTC)
    mock_email = MagicMock()
    mock_email.id = overrides.get("id", uuid4())
    mock_email.message_id = overrides.get("message_id", "<msg@t.com>")
    mock_email.in_reply_to = overrides.get("in_reply_to")
    mock_email.from_email = overrides.get("from_email", "sender@t.com")
    mock_email.from_name = overrides.get("from_name", "Sender")
    mock_email.to_emails = overrides.get("to_emails", [{"Address": "to@t.com", "Name": None}])
    mock_email.cc_emails = overrides.get("cc_emails", [])
    mock_email.reply_to_email = overrides.get("reply_to_email")
    mock_email.reply_to_name = overrides.get("reply_to_name")
    mock_email.subject = overrides.get("subject", "Test")
    mock_email.html_body = overrides.get("html_body", "<p>Hello</p>")
    mock_email.text_body = overrides.get("text_body", "Hello")
    mock_email.headers = overrides.get("headers", {})
    mock_email.sent_at_date = overrides.get("sent_at_date", "2024-01-01")
    mock_email.spam_score = overrides.get("spam_score", 0.0)
    mock_email.status = overrides.get("status", "received")
    mock_email.webhook_response_code = overrides.get("webhook_response_code")
    mock_email.error_message = overrides.get("error_message")
    mock_email.retry_count = overrides.get("retry_count", 0)
    mock_email.received_at = overrides.get("received_at", now)
    mock_email.forwarded_at = overrides.get("forwarded_at")
    mock_email.created_at = overrides.get("created_at", now)
    return mock_email


class TestListInboundEmails:
    """Tests for GET /api/v1/inbound/emails."""

    async def test_list_inbound_emails_empty(self, admin_client: AsyncClient, mock_db_session):
        """Paginated list returns empty when no inbound emails exist."""
        # The list route does count + list (2 execute calls).
        # When the list is empty the attachment-count loop body never runs,
        # so only 2 calls total.
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))

        response = await admin_client.get("/api/v1/inbound/emails")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["pages"] == 1

    async def test_list_inbound_emails_with_status_filter(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """GET /api/v1/inbound/emails?status=received triggers the status filter branch."""
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await admin_client.get("/api/v1/inbound/emails?status=received")
        assert response.status_code == 200

    async def test_list_inbound_emails_with_from_email_filter(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """GET /api/v1/inbound/emails?from_email=sender triggers the from_email filter branch."""
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await admin_client.get("/api/v1/inbound/emails?from_email=sender")
        assert response.status_code == 200

    async def test_list_inbound_emails_with_items(self, admin_client: AsyncClient, mock_db_session):
        """List with items triggers the attachment count loop body."""
        email_mock = _make_inbound_email_mock()

        # For the list endpoint: count result, list result, then attachment count per item
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [email_mock]
        att_count_result = MagicMock()
        att_count_result.scalar.return_value = 2

        mock_db_session.execute = AsyncMock(
            side_effect=[count_result, list_result, att_count_result]
        )
        response = await admin_client.get("/api/v1/inbound/emails")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["attachment_count"] == 2


class TestGetInboundEmail:
    """Tests for GET /api/v1/inbound/emails/{email_id}."""

    async def test_get_inbound_email_found(self, admin_client: AsyncClient, mock_db_session):
        """Returns inbound email details when found by ID."""
        email_id = uuid4()
        mock_email = _make_inbound_email_mock(id=email_id)
        mock_db_session.get = AsyncMock(return_value=mock_email)

        # After db.get, the route does execute to fetch attachments
        att_result = MagicMock()
        att_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=att_result)

        response = await admin_client.get(f"/api/v1/inbound/emails/{email_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(email_id)
        assert data["from_email"] == "sender@t.com"
        assert data["subject"] == "Test"
        assert data["attachments"] == []

    async def test_get_inbound_email_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Returns 404 when inbound email ID does not exist."""
        mock_db_session.get = AsyncMock(return_value=None)

        email_id = uuid4()
        response = await admin_client.get(f"/api/v1/inbound/emails/{email_id}")

        assert response.status_code == 404


class TestInboundMailboxIsAdministrationOnly:
    """The mailbox is shared by the platform: a regular client cannot read it."""

    async def test_list_requires_the_administration_scope(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await auth_client.get("/api/v1/inbound/emails")
        assert response.status_code == 403
        mock_db_session.execute.assert_not_called()

    async def test_detail_requires_the_administration_scope(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await auth_client.get(f"/api/v1/inbound/emails/{uuid4()}")
        assert response.status_code == 403
        mock_db_session.get.assert_not_called()


class TestDownloadAttachment:
    """Tests for GET /api/v1/inbound/attachments/{download_token}."""

    async def test_download_attachment_not_found(self, client: AsyncClient, mock_db_session):
        """Returns 404 when attachment token does not exist."""
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=execute_result)

        token = uuid4()
        response = await client.get(f"/api/v1/inbound/attachments/{token}")

        assert response.status_code == 404

    async def test_download_attachment_expired(self, client: AsyncClient, mock_db_session):
        """Returns 410 when attachment link has expired."""
        from datetime import timedelta

        att = MagicMock()
        att.expires_at = datetime.now(UTC) - timedelta(hours=1)
        att.file_path = "/tmp/test.txt"
        att.filename = "test.txt"
        att.content_type = "text/plain"
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = att
        mock_db_session.execute = AsyncMock(return_value=execute_result)

        token = uuid4()
        response = await client.get(f"/api/v1/inbound/attachments/{token}")
        assert response.status_code == 410

    async def test_download_attachment_file_missing(self, client: AsyncClient, mock_db_session):
        """Returns 404 when attachment file no longer exists on disk."""
        from datetime import timedelta

        att = MagicMock()
        att.expires_at = datetime.now(UTC) + timedelta(hours=1)
        att.file_path = "/tmp/nonexistent_file_for_test_12345.txt"
        att.filename = "test.txt"
        att.content_type = "text/plain"
        att.download_token = uuid4()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = att
        mock_db_session.execute = AsyncMock(return_value=execute_result)

        token = uuid4()
        response = await client.get(f"/api/v1/inbound/attachments/{token}")
        assert response.status_code == 404

    async def test_download_attachment_success(
        self, client: AsyncClient, mock_db_session, tmp_path
    ):
        """Cover line 71: successful FileResponse when file exists and is not expired."""
        from datetime import timedelta

        # Create a real temporary file on disk
        test_file = tmp_path / "attachment.txt"
        test_file.write_text("file content here")

        att = MagicMock()
        att.expires_at = datetime.now(UTC) + timedelta(hours=1)
        att.file_path = str(test_file)
        att.filename = "attachment.txt"
        att.content_type = "text/plain"
        att.download_token = uuid4()

        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = att
        mock_db_session.execute = AsyncMock(return_value=execute_result)

        token = uuid4()
        response = await client.get(f"/api/v1/inbound/attachments/{token}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "file content here" in response.text
