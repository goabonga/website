# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler/services/webhook_signature.py."""

from unittest.mock import patch

SETTINGS_PATH = "mailler.services.webhook_signature.settings"


class TestGenerateWebhookSignature:
    """Tests for generate_webhook_signature()."""

    def test_generates_hmac(self):
        """Generates a non-empty HMAC hex signature when secret is configured."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "my-secret-key"

            from mailler.services.webhook_signature import generate_webhook_signature

            sig = generate_webhook_signature("email-123", "user@example.com")

        assert isinstance(sig, str)
        assert len(sig) > 0
        # HMAC-SHA256 hex digest is always 64 characters
        assert len(sig) == 64

    def test_returns_empty_without_secret(self):
        """Returns empty string when webhook_hmac_secret is not configured."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import generate_webhook_signature

            sig = generate_webhook_signature("email-123", "user@example.com")

        assert sig == ""


class TestVerifyWebhookSignature:
    """Tests for verify_webhook_signature()."""

    def test_valid_signature(self):
        """Returns True for a valid signature."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "test-secret"

            from mailler.services.webhook_signature import (
                generate_webhook_signature,
                verify_webhook_signature,
            )

            sig = generate_webhook_signature("email-456", "recipient@test.com")
            result = verify_webhook_signature("email-456", "recipient@test.com", sig)

        assert result is True

    def test_invalid_signature(self):
        """Returns False for an invalid signature."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "test-secret"

            from mailler.services.webhook_signature import verify_webhook_signature

            result = verify_webhook_signature("email-456", "recipient@test.com", "bad-signature")

        assert result is False

    def test_returns_true_without_secret(self):
        """Returns True when no secret is configured (verification skipped)."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import verify_webhook_signature

            result = verify_webhook_signature("email-456", "recipient@test.com", "any-sig")

        assert result is True

    def test_returns_false_without_signature(self):
        """Returns False when signature is empty but secret is configured."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "test-secret"

            from mailler.services.webhook_signature import verify_webhook_signature

            result = verify_webhook_signature("email-456", "recipient@test.com", "")

        assert result is False

    def test_returns_true_when_generate_returns_empty(self):
        """Cover line 75: verify returns True when generate_webhook_signature returns empty."""
        with (
            patch(SETTINGS_PATH) as mock_settings,
            patch(
                "mailler.services.webhook_signature.generate_webhook_signature",
                return_value="",
            ),
        ):
            mock_settings.webhook_hmac_secret = "test-secret"

            from mailler.services.webhook_signature import verify_webhook_signature

            result = verify_webhook_signature("email-456", "recipient@test.com", "some-sig")

        assert result is True


class TestBuildMailinCustom:
    """Tests for build_mailin_custom()."""

    def test_basic(self):
        """Builds header with just email_id when no secret is configured."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import build_mailin_custom

            header = build_mailin_custom("abc-123", "user@test.com")

        assert header == "email_id:abc-123"

    def test_with_signature(self):
        """Includes signature when webhook secret is configured."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "secret"

            from mailler.services.webhook_signature import build_mailin_custom

            header = build_mailin_custom("abc-123", "user@test.com")

        assert header.startswith("email_id:abc-123,signature:")
        # The signature portion should be a 64-char hex string
        parts = header.split(",")
        assert len(parts) == 2
        sig_value = parts[1].split(":")[1]
        assert len(sig_value) == 64

    def test_with_extra(self):
        """Includes extra key-value pairs in the header."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import build_mailin_custom

            header = build_mailin_custom("abc-123", "user@test.com", extra={"campaign": "welcome"})

        assert "email_id:abc-123" in header
        assert "campaign:welcome" in header

    def test_escapes_special_chars(self):
        """Colons and commas in extra values are escaped."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import build_mailin_custom

            header = build_mailin_custom(
                "abc-123",
                "user@test.com",
                extra={"url": "http://example.com:8080/path,arg"},
            )

        assert "url:http\\://example.com\\:8080/path\\,arg" in header

    def test_extra_with_none_value(self):
        """Cover branch line 112->111: extra dict entry with None value is skipped."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import build_mailin_custom

            header = build_mailin_custom(
                "abc-123",
                "user@test.com",
                extra={"kept": "yes", "skipped": None},
            )

        assert "email_id:abc-123" in header
        assert "kept:yes" in header
        assert "skipped" not in header


class TestParseMailinCustom:
    """Tests for parse_mailin_custom()."""

    def test_basic_parsing(self):
        """Parses a simple key:value,key:value header."""
        from mailler.services.webhook_signature import parse_mailin_custom

        result = parse_mailin_custom("email_id:abc-123,signature:deadbeef")
        assert result == {"email_id": "abc-123", "signature": "deadbeef"}

    def test_escaped_values(self):
        """Handles escaped colons and commas in values."""
        from mailler.services.webhook_signature import parse_mailin_custom

        result = parse_mailin_custom("url:http\\://example.com\\:8080/path\\,arg")
        assert result["url"] == "http://example.com:8080/path,arg"

    def test_empty_input(self):
        """Returns empty dict for empty input."""
        from mailler.services.webhook_signature import parse_mailin_custom

        result = parse_mailin_custom("")
        assert result == {}

    def test_trailing_comma(self):
        """Cover branch line 165->168: trailing comma leaves empty current_key at end."""
        from mailler.services.webhook_signature import parse_mailin_custom

        result = parse_mailin_custom("email_id:abc-123,signature:deadbeef,")
        assert result == {"email_id": "abc-123", "signature": "deadbeef"}
        # The trailing comma creates an empty key which should be excluded

    def test_round_trip(self):
        """Build then parse preserves the original values."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "secret"

            from mailler.services.webhook_signature import (
                build_mailin_custom,
                parse_mailin_custom,
            )

            header = build_mailin_custom(
                "uuid-99",
                "user@example.com",
                extra={"ref": "val:with,special"},
            )
            parsed = parse_mailin_custom(header)

        assert parsed["email_id"] == "uuid-99"
        assert "signature" in parsed
        assert parsed["ref"] == "val:with,special"


class TestUnsubscribeSignature:
    """Tests for generate_unsubscribe_signature() and verify_unsubscribe_signature()."""

    def test_generate(self):
        """Generates a truncated (32-char) HMAC signature."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "unsub-secret"

            from mailler.services.webhook_signature import generate_unsubscribe_signature

            sig = generate_unsubscribe_signature("user@example.com", "app-one")

        assert isinstance(sig, str)
        assert len(sig) == 32

    def test_generate_returns_empty_without_secret(self):
        """Returns empty string when secret is not configured."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import generate_unsubscribe_signature

            sig = generate_unsubscribe_signature("user@example.com", "app-one")

        assert sig == ""

    def test_verify_valid(self):
        """Returns True for a valid unsubscribe signature."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "unsub-secret"

            from mailler.services.webhook_signature import (
                generate_unsubscribe_signature,
                verify_unsubscribe_signature,
            )

            sig = generate_unsubscribe_signature("user@example.com", "app-one")
            result = verify_unsubscribe_signature("user@example.com", "app-one", sig)

        assert result is True

    def test_signature_is_bound_to_the_client(self):
        """The same email gets a different signature for each client."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "unsub-secret"

            from mailler.services.webhook_signature import (
                generate_unsubscribe_signature,
                verify_unsubscribe_signature,
            )

            sig = generate_unsubscribe_signature("user@example.com", "app-one")
            other = generate_unsubscribe_signature("user@example.com", "app-two")

            assert sig != other
            assert verify_unsubscribe_signature("user@example.com", "app-two", sig) is False

    def test_verify_invalid(self):
        """Returns False for an invalid unsubscribe signature."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "unsub-secret"

            from mailler.services.webhook_signature import verify_unsubscribe_signature

            result = verify_unsubscribe_signature("user@example.com", "app-one", "wrong-sig")

        assert result is False

    def test_verify_returns_false_without_secret(self):
        """Returns False when secret is not configured (rejects unsubscribe)."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""

            from mailler.services.webhook_signature import verify_unsubscribe_signature

            result = verify_unsubscribe_signature("user@example.com", "app-one", "some-sig")

        assert result is False

    def test_verify_returns_false_without_signature(self):
        """Returns False when no signature is provided."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "unsub-secret"

            from mailler.services.webhook_signature import verify_unsubscribe_signature

            result = verify_unsubscribe_signature("user@example.com", "app-one", "")

        assert result is False

    def test_verify_returns_false_when_generate_returns_empty(self):
        """Cover line 226: verify returns False when generate_unsubscribe_signature returns empty."""
        with (
            patch(SETTINGS_PATH) as mock_settings,
            patch(
                "mailler.services.webhook_signature.generate_unsubscribe_signature",
                return_value="",
            ),
        ):
            mock_settings.webhook_hmac_secret = "unsub-secret"

            from mailler.services.webhook_signature import verify_unsubscribe_signature

            result = verify_unsubscribe_signature("user@example.com", "app-one", "some-sig")

        assert result is False


class TestBuildUnsubscribeUrl:
    """Tests for build_unsubscribe_url()."""

    def test_builds_url(self):
        """Builds a complete unsubscribe URL with email and signature."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "url-secret"
            mock_settings.unsubscribe_base_url = "https://mail.example.com"

            from mailler.services.webhook_signature import build_unsubscribe_url

            url = build_unsubscribe_url("user@example.com", "app-one")

        assert url.startswith("https://mail.example.com/unsubscribe?email=")
        assert "user%40example.com" in url
        assert "&client=app-one" in url
        assert "&sig=" in url

    def test_returns_empty_without_base_url(self):
        """Returns empty string when unsubscribe_base_url is not set."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = "url-secret"
            mock_settings.unsubscribe_base_url = ""

            from mailler.services.webhook_signature import build_unsubscribe_url

            url = build_unsubscribe_url("user@example.com", "app-one")

        assert url == ""

    def test_returns_empty_without_secret(self):
        """Returns empty string when webhook_hmac_secret is not set."""
        with patch(SETTINGS_PATH) as mock_settings:
            mock_settings.webhook_hmac_secret = ""
            mock_settings.unsubscribe_base_url = "https://mail.example.com"

            from mailler.services.webhook_signature import build_unsubscribe_url

            url = build_unsubscribe_url("user@example.com", "app-one")

        assert url == ""
