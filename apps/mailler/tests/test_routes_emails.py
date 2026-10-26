# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GET /api/v1/emails and GET /api/v1/emails/{email_id} routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _make_db_list_response(items=None, total=0):
    """Create mock DB response for paginated list queries (count + list)."""
    count_result = MagicMock()
    count_result.scalar.return_value = total

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items or []

    return [count_result, list_result]


class TestListEmails:
    """Tests for GET /api/v1/emails endpoint."""

    @pytest.mark.asyncio
    async def test_list_emails_empty(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/emails should return empty list when no emails exist."""
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))

        response = await auth_client.get("/api/v1/emails")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["pages"] == 1

    @pytest.mark.asyncio
    async def test_list_emails_with_provider_filter(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """GET /api/v1/emails?provider=brevo triggers the provider filter branch."""
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/emails?provider=brevo")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_emails_with_status_filter(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/emails?status=sent triggers the status filter branch."""
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/emails?status=sent")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_emails_with_both_filters(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/emails?provider=ses&status=failed triggers both filter branches."""
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/emails?provider=ses&status=failed")
        assert response.status_code == 200


def _statement_params(mock_db_session, call=0):
    """Bound parameters of the statement passed to the n-th ``execute`` call."""
    return mock_db_session.execute.await_args_list[call].args[0].compile().params


class TestEmailsAreScopedToTheCallingClient:
    """A client only lists the emails it owns; administrators see every client."""

    @pytest.mark.asyncio
    async def test_list_is_restricted_to_the_client_of_the_token(
        self, auth_client: AsyncClient, mock_db_session
    ):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        response = await auth_client.get("/api/v1/emails")
        assert response.status_code == 200
        # both the count and the page are restricted
        assert _statement_params(mock_db_session, 0)["client_id_1"] == "test-client-id"
        assert _statement_params(mock_db_session, 1)["client_id_1"] == "test-client-id"

    @pytest.mark.asyncio
    async def test_list_of_another_client_is_forbidden(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await auth_client.get("/api/v1/emails?client_id=other-client")
        assert response.status_code == 403
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_lists_every_client(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        response = await admin_client.get("/api/v1/emails")
        assert response.status_code == 200
        assert "client_id_1" not in _statement_params(mock_db_session, 1)

    @pytest.mark.asyncio
    async def test_admin_can_narrow_to_one_client(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        response = await admin_client.get("/api/v1/emails?client_id=other-client")
        assert response.status_code == 200
        assert _statement_params(mock_db_session, 1)["client_id_1"] == "other-client"

    @pytest.mark.asyncio
    async def test_detail_of_another_client_is_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        foreign = MagicMock()
        foreign.client_id = "other-client"
        mock_db_session.get = AsyncMock(return_value=foreign)
        response = await auth_client.get(f"/api/v1/emails/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_detail_of_an_unowned_email_is_not_found(
        self, auth_client: AsyncClient, mock_db_session
    ):
        orphan = MagicMock()
        orphan.client_id = None
        mock_db_session.get = AsyncMock(return_value=orphan)
        response = await auth_client.get(f"/api/v1/emails/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_reads_the_detail_of_any_client(
        self, admin_client: AsyncClient, mock_db_session
    ):
        now = datetime.now(UTC)
        email = MagicMock()
        for name, value in {
            "id": uuid4(),
            "to_email": "user@example.com",
            "to_name": None,
            "from_email": None,
            "from_name": None,
            "reply_to": None,
            "subject": "Test",
            "html_content": "<p>x</p>",
            "text_content": None,
            "provider": "brevo",
            "provider_message_id": None,
            "status": "sent",
            "error_message": None,
            "retry_count": 0,
            "scheduled_at": None,
            "queued_at": None,
            "sent_at": now,
            "delivered_at": None,
            "bounced_at": None,
            "failed_at": None,
            "created_at": now,
            "metadata_": {},
            "client_id": "other-client",
            "user_id": None,
            "task_id": None,
        }.items():
            setattr(email, name, value)
        mock_db_session.get = AsyncMock(return_value=email)
        response = await admin_client.get(f"/api/v1/emails/{email.id}")
        assert response.status_code == 200
        assert response.json()["client_id"] == "other-client"


class TestGetEmail:
    """Tests for GET /api/v1/emails/{email_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_email_found(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/emails/{id} should return email details when found."""
        email_id = uuid4()
        now = datetime.now(UTC)

        mock_email = MagicMock()
        mock_email.id = email_id
        mock_email.to_email = "user@example.com"
        mock_email.to_name = "User"
        mock_email.from_email = "sender@example.com"
        mock_email.from_name = "Sender"
        mock_email.reply_to = None
        mock_email.subject = "Test"
        mock_email.html_content = "<p>Test</p>"
        mock_email.text_content = None
        mock_email.provider = "brevo"
        mock_email.provider_message_id = None
        mock_email.status = "sent"
        mock_email.error_message = None
        mock_email.retry_count = 0
        mock_email.scheduled_at = None
        mock_email.queued_at = None
        mock_email.sent_at = now
        mock_email.delivered_at = None
        mock_email.bounced_at = None
        mock_email.failed_at = None
        mock_email.created_at = now
        mock_email.metadata_ = {}
        mock_email.client_id = "test-client-id"
        mock_email.user_id = None
        mock_email.task_id = "task-abc"

        mock_db_session.get = AsyncMock(return_value=mock_email)

        response = await auth_client.get(f"/api/v1/emails/{email_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(email_id)
        assert data["to_email"] == "user@example.com"
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_get_email_not_found(self, auth_client: AsyncClient, mock_db_session):
        """GET /api/v1/emails/{id} should return 404 when email not found."""
        mock_db_session.get = AsyncMock(return_value=None)

        email_id = uuid4()
        response = await auth_client.get(f"/api/v1/emails/{email_id}")

        assert response.status_code == 404
