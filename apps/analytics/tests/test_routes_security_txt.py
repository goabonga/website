# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.routes.security_txt module."""

from unittest.mock import patch

from analytics.routes.security_txt import generate_security_txt


class TestGenerateSecurityTxt:
    """Tests for generate_security_txt function."""

    def test_empty_when_nothing_configured(self):
        with patch("analytics.routes.security_txt.settings") as mock_settings:
            mock_settings.security_contact = ""
            mock_settings.security_expires = ""
            mock_settings.security_encryption = ""
            mock_settings.security_acknowledgments = ""
            mock_settings.security_preferred_languages = ""
            mock_settings.security_canonical = ""
            mock_settings.security_policy = ""
            mock_settings.security_hiring = ""
            mock_settings.security_csaf = ""
            result = generate_security_txt()
        assert result == ""

    def test_contact_only(self):
        with patch("analytics.routes.security_txt.settings") as mock_settings:
            mock_settings.security_contact = "mailto:security@example.com"
            mock_settings.security_expires = ""
            mock_settings.security_encryption = ""
            mock_settings.security_acknowledgments = ""
            mock_settings.security_preferred_languages = ""
            mock_settings.security_canonical = ""
            mock_settings.security_policy = ""
            mock_settings.security_hiring = ""
            mock_settings.security_csaf = ""
            result = generate_security_txt()
        assert result == "Contact: mailto:security@example.com"

    def test_all_fields(self):
        with patch("analytics.routes.security_txt.settings") as mock_settings:
            mock_settings.security_contact = "mailto:security@example.com"
            mock_settings.security_expires = "2026-12-31T23:59:59Z"
            mock_settings.security_encryption = "https://example.com/pgp-key.txt"
            mock_settings.security_acknowledgments = "https://example.com/thanks"
            mock_settings.security_preferred_languages = "en, fr"
            mock_settings.security_canonical = "https://example.com/.well-known/security.txt"
            mock_settings.security_policy = "https://example.com/security-policy"
            mock_settings.security_hiring = "https://example.com/jobs"
            mock_settings.security_csaf = "https://example.com/.well-known/csaf"
            result = generate_security_txt()
        assert "Contact: mailto:security@example.com" in result
        assert "Expires: 2026-12-31T23:59:59Z" in result
        assert "Encryption: https://example.com/pgp-key.txt" in result
        assert "Acknowledgments: https://example.com/thanks" in result
        assert "Preferred-Languages: en, fr" in result
        assert "Canonical: https://example.com/.well-known/security.txt" in result
        assert "Policy: https://example.com/security-policy" in result
        assert "Hiring: https://example.com/jobs" in result
        assert "CSAF: https://example.com/.well-known/csaf" in result


class TestSecurityTxtEndpoint:
    """Tests for security_txt endpoint."""

    async def test_returns_plain_text(self):
        from analytics.routes.security_txt import security_txt

        with patch("analytics.routes.security_txt.settings") as mock_settings:
            mock_settings.security_contact = "mailto:test@example.com"
            mock_settings.security_expires = ""
            mock_settings.security_encryption = ""
            mock_settings.security_acknowledgments = ""
            mock_settings.security_preferred_languages = ""
            mock_settings.security_canonical = ""
            mock_settings.security_policy = ""
            mock_settings.security_hiring = ""
            mock_settings.security_csaf = ""
            response = await security_txt()
        assert response.media_type == "text/plain"
        assert b"Contact: mailto:test@example.com" in response.body
