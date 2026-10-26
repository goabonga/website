# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for POST /api/v1/send route."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


class TestSendEmail:
    """Tests for POST /api/v1/send endpoint."""

    @pytest.mark.asyncio
    async def test_send_email_success(self, auth_client: AsyncClient, mock_db_session):
        """POST /api/v1/send should create an email, queue a task, and return 200."""
        with patch("mailler.routes.send.send_email_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-123")

            payload = {
                "to_email": "recipient@example.com",
                "to_name": "Recipient",
                "subject": "Test Subject",
                "html_content": "<p>Hello</p>",
                "provider": "brevo",
            }

            response = await auth_client.post("/api/v1/send", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert data["status"] == "queued"
            assert data["task_id"] == "celery-task-123"

            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_awaited_once()
            mock_db_session.refresh.assert_awaited_once()
            mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_is_recorded_for_the_calling_client(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """The stored email belongs to the client of the token and gets the identity of its record."""
        with patch("mailler.routes.send.send_email_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-123")
            response = await auth_client.post(
                "/api/v1/send",
                json={
                    "to_email": "recipient@example.com",
                    "subject": "Test Subject",
                    "html_content": "<p>Hello</p>",
                    "provider": "brevo",
                },
            )

        assert response.status_code == 200
        email = mock_db_session.add.call_args[0][0]
        assert email.client_id == "test-client-id"
        assert email.from_email == "app@client.example"
        assert email.from_name == "Client App"
        assert email.provider == "brevo"

    @pytest.mark.asyncio
    async def test_send_email_without_any_sender_is_refused(
        self, auth_client: AsyncClient, mock_db_session, client_record
    ):
        """Without a request sender and without a sender in its record nothing is stored."""
        client_record.from_email = None
        response = await auth_client.post(
            "/api/v1/send",
            json={
                "to_email": "recipient@example.com",
                "subject": "Test Subject",
                "html_content": "<p>Hello</p>",
                "provider": "brevo",
            },
        )

        assert response.status_code == 422
        assert "No sender address" in response.json()["detail"]
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_email_unauthenticated(self, client: AsyncClient):
        """POST /api/v1/send without auth should return 401."""
        payload = {
            "to_email": "recipient@example.com",
            "subject": "Test Subject",
            "html_content": "<p>Hello</p>",
            "provider": "brevo",
        }

        response = await client.post("/api/v1/send", json=payload)

        assert response.status_code == 401


_BODY = {
    "to_email": "recipient@example.com",
    "subject": "Test Subject",
    "html_content": "<p>Hello</p>",
}


class TestSendUsesTheClientRecord:
    """The sender and the provider come from the registry record of the client."""

    async def _send(self, client, **extra):
        with patch("mailler.routes.send.send_email_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-1")
            return await client.post("/api/v1/send", json={**_BODY, **extra})

    async def test_provider_is_optional(self, auth_client: AsyncClient, mock_db_session):
        response = await self._send(auth_client)
        assert response.status_code == 200
        assert mock_db_session.add.call_args[0][0].provider == "brevo"

    async def test_another_allowed_provider_can_be_chosen(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await self._send(auth_client, provider="ses")
        assert response.status_code == 200
        assert mock_db_session.add.call_args[0][0].provider == "ses"

    async def test_provider_outside_the_record_is_refused(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await self._send(auth_client, provider="sendgrid")
        assert response.status_code == 403
        assert "Provider" in response.json()["detail"]
        mock_db_session.add.assert_not_called()

    async def test_another_identity_of_the_record_can_be_chosen(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await self._send(auth_client, from_email="alerts@client.example")
        assert response.status_code == 200
        email = mock_db_session.add.call_args[0][0]
        assert (email.from_email, email.from_name) == ("alerts@client.example", "Client Alerts")

    async def test_arbitrary_sender_is_refused(self, auth_client: AsyncClient, mock_db_session):
        response = await self._send(auth_client, from_email="ceo@bank.example")
        assert response.status_code == 403
        assert "Sender address" in response.json()["detail"]
        mock_db_session.add.assert_not_called()

    async def test_arbitrary_sender_name_is_refused(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await self._send(auth_client, from_name="Your Bank")
        assert response.status_code == 403
        assert "Sender name" in response.json()["detail"]

    async def test_fixed_reply_to_is_enforced(
        self, auth_client: AsyncClient, mock_db_session, client_record
    ):
        client_record.reply_to = "support@client.example"
        response = await self._send(auth_client, reply_to="phish@evil.example")
        assert response.status_code == 403
        response = await self._send(auth_client)
        assert response.status_code == 200
        assert mock_db_session.add.call_args[0][0].reply_to == "support@client.example"

    async def test_client_without_provider_is_refused(
        self, auth_client: AsyncClient, mock_db_session, client_record
    ):
        client_record.default_provider = None
        response = await self._send(auth_client)
        assert response.status_code == 422
        assert "No provider" in response.json()["detail"]

    async def test_administrators_are_not_bound_by_a_record(
        self, admin_client: AsyncClient, mock_db_session
    ):
        response = await self._send(
            admin_client, from_email="ops@platform.example", provider="sendgrid"
        )
        assert response.status_code == 200
        email = mock_db_session.add.call_args[0][0]
        assert (email.from_email, email.provider) == ("ops@platform.example", "sendgrid")


class TestSendIsLimited:
    """The rate limit and the daily quota of the client record are enforced."""

    @staticmethod
    def _counting(mock_db_session, *counts):
        results = []
        for count in counts:
            result = MagicMock()
            result.scalar.return_value = count
            results.append(result)
        mock_db_session.execute = AsyncMock(side_effect=results)

    async def _send(self, client):
        with patch("mailler.routes.send.send_email_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-1")
            return await client.post("/api/v1/send", json=_BODY)

    async def test_under_the_limits(self, auth_client: AsyncClient, mock_db_session, client_record):
        client_record.rate_limit_per_minute = 5
        client_record.daily_quota = 100
        self._counting(mock_db_session, 4, 99)
        assert (await self._send(auth_client)).status_code == 200

    async def test_rate_limit(self, auth_client: AsyncClient, mock_db_session, client_record):
        client_record.rate_limit_per_minute = 5
        self._counting(mock_db_session, 5)
        response = await self._send(auth_client)
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
        mock_db_session.add.assert_not_called()

    async def test_daily_quota(self, auth_client: AsyncClient, mock_db_session, client_record):
        client_record.daily_quota = 100
        self._counting(mock_db_session, 100)
        response = await self._send(auth_client)
        assert response.status_code == 429
        assert "Daily quota" in response.json()["detail"]
        mock_db_session.add.assert_not_called()

    async def test_administrators_are_not_limited(
        self, admin_client: AsyncClient, mock_db_session, client_record
    ):
        client_record.rate_limit_per_minute = 1
        client_record.daily_quota = 1
        self._counting(mock_db_session)
        assert (await self._send(admin_client)).status_code == 200


class TestSendFromATemplate:
    """POST /send renders one of the templates of the client."""

    @staticmethod
    def _template(**fields):
        template = MagicMock()
        template.slug = "workspace_invitation"
        template.status = "active"
        template.subject_template = "Join {{ workspace }}"
        template.html_compiled = "<p>Join {{ workspace }}: {{ link }}</p>"
        template.plain_text = "Join %workspace%"
        template.variables = ["workspace", "link"]
        for key, value in fields.items():
            setattr(template, key, value)
        return template

    @staticmethod
    def _found(mock_db_session, template):
        result = MagicMock()
        result.scalar_one_or_none.return_value = template
        mock_db_session.execute = AsyncMock(return_value=result)

    async def _send(self, client, **body):
        with patch("mailler.routes.send.send_email_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-1")
            return await client.post(
                "/api/v1/send",
                json={
                    "to_email": "recipient@example.com",
                    "template_slug": "workspace_invitation",
                    **body,
                },
            )

    async def test_the_rendered_email_is_stored(self, auth_client: AsyncClient, mock_db_session):
        self._found(mock_db_session, self._template())
        response = await self._send(
            auth_client, variables={"workspace": "Acme", "link": "https://app.example/join?a=1&b=2"}
        )
        assert response.status_code == 200
        assert response.json()["missing_variables"] == []
        email = mock_db_session.add.call_args[0][0]
        assert email.subject == "Join Acme"
        assert email.html_content == "<p>Join Acme: https://app.example/join?a=1&amp;b=2</p>"
        assert email.text_content == "Join Acme"
        assert email.metadata_ == {"template_slug": "workspace_invitation"}
        assert (email.from_email, email.provider) == ("app@client.example", "brevo")

    async def test_missing_variables_are_listed(self, auth_client: AsyncClient, mock_db_session):
        self._found(mock_db_session, self._template())
        response = await self._send(auth_client, variables={"workspace": "Acme"})
        assert response.status_code == 200
        assert response.json()["missing_variables"] == ["link"]

    async def test_unknown_template(self, auth_client: AsyncClient, mock_db_session):
        self._found(mock_db_session, None)
        response = await self._send(auth_client)
        assert response.status_code == 404
        mock_db_session.add.assert_not_called()

    async def test_draft_template(self, auth_client: AsyncClient, mock_db_session):
        self._found(mock_db_session, self._template(status="draft"))
        response = await self._send(auth_client)
        assert response.status_code == 422
        mock_db_session.add.assert_not_called()

    async def test_content_and_template_are_exclusive(
        self, auth_client: AsyncClient, mock_db_session
    ):
        response = await self._send(auth_client, subject="Hi")
        assert response.status_code == 422
        mock_db_session.add.assert_not_called()

    async def test_the_sender_rules_still_apply(self, auth_client: AsyncClient, mock_db_session):
        self._found(mock_db_session, self._template())
        response = await self._send(auth_client, from_email="ceo@bank.example")
        assert response.status_code == 403
        mock_db_session.add.assert_not_called()
