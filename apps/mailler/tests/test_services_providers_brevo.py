# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.services.providers.brevo module."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from mailler.services.providers.brevo import BrevoProvider


class TestBrevoProviderProperties:
    """Tests for BrevoProvider properties."""

    def test_provider_name(self):
        provider = BrevoProvider(api_key="key")
        assert provider.provider_name == "brevo"

    def test_is_configured_with_key(self):
        provider = BrevoProvider(api_key="test-key")
        assert provider.is_configured is True

    def test_not_configured_without_key(self):
        provider = BrevoProvider(api_key="")
        assert provider.is_configured is False


class TestBrevoSendEmail:
    """Tests for BrevoProvider.send_email."""

    def test_not_configured_returns_error(self):
        provider = BrevoProvider(api_key="")
        result = provider.send_email("to@test.com", "Subject", "<html>Body</html>")
        assert result.success is False
        assert "not configured" in result.error_message

    def test_successful_send(self):
        provider = BrevoProvider(
            api_key="test-key",
            default_from="from@test.com",
            default_from_name="Test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "<msg-123>"}

        with patch("mailler.services.providers.brevo.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = provider.send_email(
                to="recipient@test.com",
                subject="Test Subject",
                html_body="<p>Hello</p>",
            )

        assert result.success is True
        assert result.provider_message_id == "<msg-123>"

    def test_send_with_all_params(self):
        provider = BrevoProvider(
            api_key="test-key",
            default_from="from@test.com",
            default_from_name="Test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "<msg-456>"}

        with (
            patch("mailler.services.providers.brevo.httpx.Client") as mock_client_cls,
            patch(
                "mailler.services.providers.brevo.build_mailin_custom", return_value="email_id:123"
            ),
        ):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = provider.send_email(
                to="recipient@test.com",
                subject="Test",
                html_body="<p>Hi</p>",
                plain_body="Hi",
                from_name="Custom",
                from_email="custom@test.com",
                reply_to="reply@test.com",
                email_id="uuid-123",
                metadata={"campaign_id": 42},
            )

        assert result.success is True

    def test_api_error(self):
        provider = BrevoProvider(api_key="test-key", default_from="f@t.com", default_from_name="T")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"message":"Bad request"}'
        mock_response.json.return_value = {"message": "Bad request"}

        with patch("mailler.services.providers.brevo.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
        assert "Bad request" in result.error_message

    def test_network_error(self):
        provider = BrevoProvider(api_key="test-key", default_from="f@t.com", default_from_name="T")

        with patch("mailler.services.providers.brevo.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.RequestError("Connection refused")
            mock_client_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
        assert "Connection refused" in result.error_message

    def test_unexpected_error(self):
        provider = BrevoProvider(api_key="test-key", default_from="f@t.com", default_from_name="T")

        with patch("mailler.services.providers.brevo.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = RuntimeError("unexpected")
            mock_client_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False

    def test_send_with_email_id_no_campaign_metadata(self):
        """Cover branch line 85->88: email_id set but metadata has no campaign_id."""
        provider = BrevoProvider(
            api_key="test-key",
            default_from="from@test.com",
            default_from_name="Test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "<msg-no-campaign>"}

        with (
            patch("mailler.services.providers.brevo.httpx.Client") as mock_client_cls,
            patch(
                "mailler.services.providers.brevo.build_mailin_custom",
                return_value="email_id:uuid-no-camp",
            ) as mock_build,
        ):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = provider.send_email(
                to="recipient@test.com",
                subject="Test",
                html_body="<p>Hi</p>",
                email_id="uuid-no-camp",
                metadata={"other_key": "value"},
            )

        assert result.success is True
        # build_mailin_custom should be called with extra=None (no campaign_id)
        mock_build.assert_called_once_with("uuid-no-camp", "recipient@test.com", extra=None)

    def test_send_with_email_id_no_metadata(self):
        """Cover branch line 85->88: email_id set but metadata is None."""
        provider = BrevoProvider(
            api_key="test-key",
            default_from="from@test.com",
            default_from_name="Test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "<msg-no-meta>"}

        with (
            patch("mailler.services.providers.brevo.httpx.Client") as mock_client_cls,
            patch(
                "mailler.services.providers.brevo.build_mailin_custom",
                return_value="email_id:uuid-no-meta",
            ) as mock_build,
        ):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = provider.send_email(
                to="recipient@test.com",
                subject="Test",
                html_body="<p>Hi</p>",
                email_id="uuid-no-meta",
                metadata=None,
            )

        assert result.success is True
        mock_build.assert_called_once_with("uuid-no-meta", "recipient@test.com", extra=None)


class TestBrevoUnblockContact:
    """Tests for BrevoProvider.unblock_contact."""

    async def test_not_configured(self):
        provider = BrevoProvider(api_key="")
        result = await provider.unblock_contact("user@test.com")
        assert result["success"] is False

    async def test_success(self):
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Contact unblocked"}

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.unblock_contact("user@test.com")

        assert result["success"] is True

    async def test_not_in_blocklist(self):
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.unblock_contact("user@test.com")

        assert result["success"] is True

    async def test_api_error(self):
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b'{"message":"Server error"}'
        mock_response.json.return_value = {"message": "Server error"}

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.unblock_contact("user@test.com")

        assert result["success"] is False

    async def test_network_error(self):
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.RequestError("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.unblock_contact("user@test.com")

        assert result["success"] is False

    async def test_unexpected_exception(self):
        """Cover lines 204-209: unexpected Exception in unblock_contact."""
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=RuntimeError("unexpected crash"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.unblock_contact("user@test.com")

        assert result["success"] is False
        assert "unexpected crash" in result["error"]


class TestBrevoGetContactStatus:
    """Tests for BrevoProvider.get_contact_status."""

    async def test_not_configured(self):
        provider = BrevoProvider(api_key="")
        result = await provider.get_contact_status("user@test.com")
        assert result["success"] is False

    async def test_found(self):
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "email": "user@test.com",
            "emailBlacklisted": False,
            "smsBlacklisted": False,
        }

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.get_contact_status("user@test.com")

        assert result["success"] is True
        assert result["email_blacklisted"] is False

    async def test_not_found(self):
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.get_contact_status("user@test.com")

        assert result["success"] is False

    async def test_other_http_error(self):
        """Cover lines 244-248: get_contact_status with non-200/non-404 status code."""
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b'{"message":"Internal server error"}'
        mock_response.json.return_value = {"message": "Internal server error"}

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.get_contact_status("user@test.com")

        assert result["success"] is False
        assert "Internal server error" in result["error"]

    async def test_exception(self):
        provider = BrevoProvider(api_key="key", default_from="f@t.com", default_from_name="T")

        with patch("mailler.services.providers.brevo.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await provider.get_contact_status("user@test.com")

        assert result["success"] is False
