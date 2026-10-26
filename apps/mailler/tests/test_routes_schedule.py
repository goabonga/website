# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for POST /api/v1/schedule route."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


class TestScheduleEmail:
    """Tests for POST /api/v1/schedule endpoint."""

    @pytest.mark.asyncio
    async def test_schedule_email_success(self, auth_client: AsyncClient, mock_db_session):
        """POST /api/v1/schedule should create a scheduled email and return 200."""
        payload = {
            "to_email": "recipient@example.com",
            "to_name": "Recipient",
            "subject": "Scheduled Subject",
            "html_content": "<p>Scheduled Hello</p>",
            "provider": "brevo",
            "scheduled_at": "2026-06-01T10:00:00Z",
        }

        response = await auth_client.post("/api/v1/schedule", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == "scheduled"
        assert data["task_id"] is None

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_schedule_email_unauthenticated(self, client: AsyncClient):
        """POST /api/v1/schedule without auth should return 401."""
        payload = {
            "to_email": "recipient@example.com",
            "subject": "Scheduled Subject",
            "html_content": "<p>Hello</p>",
            "provider": "brevo",
            "scheduled_at": "2026-06-01T10:00:00Z",
        }

        response = await client.post("/api/v1/schedule", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_schedule_email_belongs_to_the_calling_client(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """The stored email is owned by the client of the token and gets its record identity."""
        response = await auth_client.post(
            "/api/v1/schedule",
            json={
                "to_email": "recipient@example.com",
                "subject": "Scheduled Subject",
                "html_content": "<p>Hello</p>",
                "provider": "brevo",
                "scheduled_at": "2026-06-01T10:00:00Z",
            },
        )

        assert response.status_code == 200
        email = mock_db_session.add.call_args[0][0]
        assert email.client_id == "test-client-id"
        assert email.from_email == "app@client.example"

    @pytest.mark.asyncio
    async def test_schedule_email_without_any_sender_is_refused(
        self, auth_client: AsyncClient, mock_db_session, client_record
    ):
        """Without a request sender and without a sender in its record nothing is stored."""
        client_record.from_email = None
        response = await auth_client.post(
            "/api/v1/schedule",
            json={
                "to_email": "recipient@example.com",
                "subject": "Scheduled Subject",
                "html_content": "<p>Hello</p>",
                "provider": "brevo",
                "scheduled_at": "2026-06-01T10:00:00Z",
            },
        )

        assert response.status_code == 422
        mock_db_session.add.assert_not_called()


class TestScheduleUsesTheClientRecord:
    """Scheduled emails follow the same sender and provider rules as immediate ones."""

    _BODY = {
        "to_email": "recipient@example.com",
        "subject": "Scheduled",
        "html_content": "<p>Hello</p>",
        "scheduled_at": "2026-06-01T10:00:00Z",
    }

    async def test_defaults_and_choices(self, auth_client: AsyncClient, mock_db_session):
        response = await auth_client.post("/api/v1/schedule", json=self._BODY)
        assert response.status_code == 200
        email = mock_db_session.add.call_args[0][0]
        assert (email.from_email, email.provider) == ("app@client.example", "brevo")

        response = await auth_client.post(
            "/api/v1/schedule",
            json={**self._BODY, "from_email": "alerts@client.example", "provider": "ses"},
        )
        assert response.status_code == 200
        email = mock_db_session.add.call_args[0][0]
        assert (email.from_email, email.provider) == ("alerts@client.example", "ses")

    async def test_arbitrary_sender_and_provider_are_refused(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await auth_client.post(
            "/api/v1/schedule", json={**self._BODY, "from_email": "ceo@bank.example"}
        )
        assert response.status_code == 403
        response = await auth_client.post(
            "/api/v1/schedule", json={**self._BODY, "provider": "sendgrid"}
        )
        assert response.status_code == 403
        mock_db_session.add.assert_not_called()


class TestScheduleIsLimited:
    async def test_scheduled_emails_count_against_the_limits(
        self, auth_client: AsyncClient, mock_db_session, client_record
    ):
        client_record.daily_quota = 10
        result = MagicMock()
        result.scalar.return_value = 10
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await auth_client.post(
            "/api/v1/schedule",
            json={
                "to_email": "recipient@example.com",
                "subject": "Scheduled",
                "html_content": "<p>Hello</p>",
                "scheduled_at": "2026-06-01T10:00:00Z",
            },
        )
        assert response.status_code == 429
        mock_db_session.add.assert_not_called()


class TestScheduleFromATemplate:
    async def test_the_template_is_rendered_when_scheduling(
        self, auth_client: AsyncClient, mock_db_session
    ):
        template = MagicMock()
        template.slug = "welcome"
        template.status = "active"
        template.subject_template = "Hello {{ name }}"
        template.html_compiled = "<p>Hello {{ name }}</p>"
        template.plain_text = None
        template.variables = ["name"]
        result = MagicMock()
        result.scalar_one_or_none.return_value = template
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.post(
            "/api/v1/schedule",
            json={
                "to_email": "recipient@example.com",
                "template_slug": "welcome",
                "variables": {"name": "Ann"},
                "scheduled_at": "2026-06-01T10:00:00Z",
            },
        )

        assert response.status_code == 200
        assert response.json()["missing_variables"] == []
        email = mock_db_session.add.call_args[0][0]
        assert (email.subject, email.html_content) == ("Hello Ann", "<p>Hello Ann</p>")
        assert email.metadata_ == {"template_slug": "welcome"}

    async def test_missing_template(self, auth_client: AsyncClient, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await auth_client.post(
            "/api/v1/schedule",
            json={
                "to_email": "recipient@example.com",
                "template_slug": "nope",
                "scheduled_at": "2026-06-01T10:00:00Z",
            },
        )
        assert response.status_code == 404
