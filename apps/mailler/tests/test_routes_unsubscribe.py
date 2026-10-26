# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for public unsubscribe routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient


def _make_contact_mock(**overrides):
    """Create a mock Contact with default values."""
    now = datetime.now(UTC)
    mock_contact = MagicMock()
    mock_contact.id = overrides.get("id", uuid4())
    mock_contact.email = overrides.get("email", "user@example.com")
    mock_contact.status = overrides.get("status", "active")
    mock_contact.first_name = overrides.get("first_name", "Test")
    mock_contact.last_name = overrides.get("last_name", "User")
    mock_contact.full_name = overrides.get("full_name", "Test User")
    mock_contact.source = overrides.get("source", "api")
    mock_contact.custom_fields = overrides.get("custom_fields", {})
    mock_contact.created_at = overrides.get("created_at", now)
    mock_contact.updated_at = overrides.get("updated_at", now)
    return mock_contact


class TestUnsubscribeConfirm:
    """Tests for GET /api/v1/unsubscribe."""

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_confirm_valid_signature(self, mock_verify, client: AsyncClient):
        """Valid signature shows the confirmation page."""
        mock_verify.return_value = True

        response = await client.get(
            "/api/v1/unsubscribe",
            params={"email": "user@example.com", "client": "app-one", "sig": "valid-sig"},
        )

        assert response.status_code == 200
        assert "user@example.com" in response.text
        mock_verify.assert_called_once_with("user@example.com", "app-one", "valid-sig")

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_confirm_form_posts_signed_parameters_in_query(
        self, mock_verify, client: AsyncClient
    ):
        """The form action carries email, client and signature, as the POST route reads them."""
        mock_verify.return_value = True

        response = await client.get(
            "/api/v1/unsubscribe",
            params={"email": "user+tag@example.com", "client": "app-one", "sig": "valid-sig"},
        )

        assert (
            'action="/api/v1/unsubscribe?email=user%2Btag%40example.com'
            '&amp;client=app-one&amp;sig=valid-sig"' in response.text
        )

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_confirm_invalid_signature(self, mock_verify, client: AsyncClient):
        """Invalid signature returns 403 error page."""
        mock_verify.return_value = False

        response = await client.get(
            "/api/v1/unsubscribe",
            params={"email": "user@example.com", "client": "app-one", "sig": "bad-sig"},
        )

        assert response.status_code == 403


class TestUnsubscribeProcess:
    """Tests for POST /api/v1/unsubscribe."""

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_process_valid_unsubscribe(
        self, mock_verify, client: AsyncClient, mock_db_session
    ):
        """Valid unsubscribe request updates contact status."""
        mock_verify.return_value = True
        mock_contact = _make_contact_mock(email="user@example.com", status="active")
        execute_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_contact))
        mock_db_session.execute = AsyncMock(return_value=execute_result)

        response = await client.post(
            "/api/v1/unsubscribe",
            params={"email": "user@example.com", "client": "app-one", "sig": "valid-sig"},
        )

        assert response.status_code == 200
        assert mock_contact.status == "unsubscribed"
        mock_db_session.commit.assert_awaited()

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_process_unknown_contact(self, mock_verify, client: AsyncClient, mock_db_session):
        """Unknown contact still returns 200 to prevent email enumeration."""
        mock_verify.return_value = True
        execute_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_db_session.execute = AsyncMock(return_value=execute_result)

        response = await client.post(
            "/api/v1/unsubscribe",
            params={"email": "unknown@example.com", "client": "app-one", "sig": "valid-sig"},
        )

        assert response.status_code == 200


class TestUnsubscribePostInvalidSignature:
    """Tests for POST /api/v1/unsubscribe with invalid signature."""

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_post_invalid_signature(self, mock_verify, client: AsyncClient):
        """POST with invalid signature returns 403."""
        mock_verify.return_value = False

        response = await client.post(
            "/api/v1/unsubscribe",
            params={"email": "user@example.com", "client": "app-one", "sig": "bad-sig"},
        )

        assert response.status_code == 403


class TestUnsubscribeAlreadyUnsubscribed:
    """Tests for POST /api/v1/unsubscribe when contact is already unsubscribed."""

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_already_unsubscribed(self, mock_verify, client: AsyncClient, mock_db_session):
        """Already-unsubscribed contact still returns 200 success page."""
        mock_verify.return_value = True
        mock_contact = MagicMock()
        mock_contact.id = uuid4()
        mock_contact.email = "user@example.com"
        mock_contact.status = "unsubscribed"
        execute_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_contact))
        mock_db_session.execute = AsyncMock(return_value=execute_result)

        response = await client.post(
            "/api/v1/unsubscribe",
            params={"email": "user@example.com", "client": "app-one", "sig": "valid-sig"},
        )

        assert response.status_code == 200
        assert "Successfully unsubscribed" in response.text


class TestUnsubscribeIsBoundToTheClient:
    """The link unsubscribes the contact of one client only."""

    async def test_client_is_required(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/unsubscribe", params={"email": "user@example.com", "sig": "sig"}
        )
        assert response.status_code == 422

    @patch("mailler.routes.unsubscribe.verify_unsubscribe_signature")
    async def test_contact_is_looked_up_inside_the_signed_client(
        self, mock_verify, client: AsyncClient, mock_db_session
    ):
        mock_verify.return_value = True
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        await client.post(
            "/api/v1/unsubscribe",
            params={"email": "User@Example.com", "client": "app-two", "sig": "valid-sig"},
        )

        mock_verify.assert_called_once_with("User@Example.com", "app-two", "valid-sig")
        params = mock_db_session.execute.await_args.args[0].compile().params
        assert params["client_id_1"] == "app-two"
        assert params["email_1"] == "user@example.com"
