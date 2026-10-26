# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for POST /api/v1/send route."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from mailler.config import settings


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
        """The stored email belongs to the client of the token and gets the platform sender."""
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
        assert email.from_email == "sender@example.test"
        assert email.from_name == "Test Sender"

    @pytest.mark.asyncio
    async def test_send_email_without_any_sender_is_refused(
        self, auth_client: AsyncClient, mock_db_session, monkeypatch
    ):
        """Without a request sender and without DEFAULT_FROM nothing is stored."""
        monkeypatch.setattr(settings, "default_from", "")
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
