# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.services.providers.ses module."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from mailler.services.providers.ses import SESProvider


class TestSESProviderProperties:
    """Tests for SESProvider properties."""

    def test_provider_name(self):
        provider = SESProvider(region="us-east-1", access_key="ak", secret_key="sk")
        assert provider.provider_name == "ses"

    def test_is_configured(self):
        assert (
            SESProvider(region="us-east-1", access_key="ak", secret_key="sk").is_configured is True
        )

    def test_not_configured_missing_access_key(self):
        with patch("mailler.services.providers.ses.settings") as ms:
            ms.ses_region = "us-east-1"
            ms.ses_access_key = ""
            ms.ses_secret_key = "sk"
            ms.default_from = "f@t.com"
            ms.default_from_name = "T"
            provider = SESProvider(region="us-east-1", access_key="", secret_key="sk")
        assert provider.is_configured is False

    def test_not_configured_missing_secret_key(self):
        with patch("mailler.services.providers.ses.settings") as ms:
            ms.ses_region = "us-east-1"
            ms.ses_access_key = "ak"
            ms.ses_secret_key = ""
            ms.default_from = "f@t.com"
            ms.default_from_name = "T"
            provider = SESProvider(region="us-east-1", access_key="ak", secret_key="")
        assert provider.is_configured is False

    def test_not_configured_missing_region(self):
        with patch("mailler.services.providers.ses.settings") as ms:
            ms.ses_region = ""
            ms.ses_access_key = "ak"
            ms.ses_secret_key = "sk"
            ms.default_from = "f@t.com"
            ms.default_from_name = "T"
            provider = SESProvider(region="", access_key="ak", secret_key="sk")
        assert provider.is_configured is False


class TestSESFormatSender:
    """Tests for SESProvider._format_sender."""

    def test_with_name(self):
        provider = SESProvider(region="r", access_key="a", secret_key="s")
        assert provider._format_sender("Test", "test@t.com") == "Test <test@t.com>"

    def test_without_name(self):
        provider = SESProvider(region="r", access_key="a", secret_key="s")
        assert provider._format_sender(None, "test@t.com") == "test@t.com"


class TestSESSendEmail:
    """Tests for SESProvider.send_email."""

    def test_not_configured(self):
        provider = SESProvider(region="", access_key="", secret_key="")
        result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")
        assert result.success is False
        assert "not configured" in result.error_message

    def test_successful_send(self):
        provider = SESProvider(
            region="us-east-1",
            access_key="ak",
            secret_key="sk",
            default_from="from@t.com",
            default_from_name="Test",
        )

        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "ses-msg-123"}

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = provider.send_email("to@t.com", "Subject", "<p>Hello</p>")

        assert result.success is True
        assert result.provider_message_id == "ses-msg-123"

    def test_send_with_plain_body(self):
        provider = SESProvider(
            region="us-east-1",
            access_key="ak",
            secret_key="sk",
            default_from="from@t.com",
            default_from_name="Test",
        )

        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "msg"}

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = provider.send_email("to@t.com", "Sub", "<p>Hi</p>", plain_body="Hi")

        assert result.success is True
        call_kwargs = mock_client.send_email.call_args[1]
        assert "Text" in call_kwargs["Message"]["Body"]

    def test_send_with_reply_to(self):
        provider = SESProvider(
            region="us-east-1",
            access_key="ak",
            secret_key="sk",
            default_from="from@t.com",
            default_from_name="Test",
        )

        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "msg"}

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = provider.send_email("to@t.com", "Sub", "<p>Hi</p>", reply_to="reply@t.com")

        assert result.success is True
        call_kwargs = mock_client.send_email.call_args[1]
        assert "reply@t.com" in call_kwargs["ReplyToAddresses"]

    def test_client_error(self):
        provider = SESProvider(
            region="us-east-1",
            access_key="ak",
            secret_key="sk",
            default_from="from@t.com",
            default_from_name="Test",
        )

        mock_client = MagicMock()
        mock_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}},
            "SendEmail",
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
        assert "MessageRejected" in result.error_message

    def test_unexpected_error(self):
        provider = SESProvider(
            region="us-east-1",
            access_key="ak",
            secret_key="sk",
            default_from="from@t.com",
            default_from_name="Test",
        )

        mock_client = MagicMock()
        mock_client.send_email.side_effect = RuntimeError("unexpected")

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False


class TestSESGetClient:
    """Tests for SESProvider._get_client."""

    def test_creates_client_lazily(self):
        provider = SESProvider(region="us-east-1", access_key="ak", secret_key="sk")
        assert provider._client is None

        with patch("mailler.services.providers.ses.boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            client = provider._get_client()
            assert client is not None
            mock_boto.assert_called_once_with(
                "ses",
                region_name="us-east-1",
                aws_access_key_id="ak",
                aws_secret_access_key="sk",
            )

    def test_reuses_client(self):
        provider = SESProvider(region="us-east-1", access_key="ak", secret_key="sk")

        with patch("mailler.services.providers.ses.boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            client1 = provider._get_client()
            client2 = provider._get_client()
            assert client1 is client2
            mock_boto.assert_called_once()
