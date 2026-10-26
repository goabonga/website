# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.routes.security_txt module."""

from unittest.mock import MagicMock, patch

import pytest
from backend.routes.security_txt import generate_security_txt, router
from httpx import ASGITransport, AsyncClient


class TestGenerateSecurityTxt:
    """Tests for the generate_security_txt function."""

    @patch("backend.routes.security_txt.settings")
    def test_all_fields_set_returns_full_content(self, mock_settings: MagicMock) -> None:
        """When all settings fields are set, every line appears in the output."""
        mock_settings.security_contact = "mailto:security@example.com"
        mock_settings.security_expires = "2025-12-31T23:59:59Z"
        mock_settings.security_encryption = "https://example.com/pgp-key.txt"
        mock_settings.security_acknowledgments = "https://example.com/thanks"
        mock_settings.security_preferred_languages = "en, fr"
        mock_settings.security_canonical = "https://example.com/.well-known/security.txt"
        mock_settings.security_policy = "https://example.com/security-policy"
        mock_settings.security_hiring = "https://example.com/jobs"
        mock_settings.security_csaf = "https://example.com/.well-known/csaf/provider-metadata.json"

        result = generate_security_txt()

        assert "Contact: mailto:security@example.com" in result
        assert "Expires: 2025-12-31T23:59:59Z" in result
        assert "Encryption: https://example.com/pgp-key.txt" in result
        assert "Acknowledgments: https://example.com/thanks" in result
        assert "Preferred-Languages: en, fr" in result
        assert "Canonical: https://example.com/.well-known/security.txt" in result
        assert "Policy: https://example.com/security-policy" in result
        assert "Hiring: https://example.com/jobs" in result
        assert "CSAF: https://example.com/.well-known/csaf/provider-metadata.json" in result
        # Ensure exactly 9 lines
        assert len(result.strip().split("\n")) == 9

    @patch("backend.routes.security_txt.settings")
    def test_only_required_fields(self, mock_settings: MagicMock) -> None:
        """When only Contact and Expires are set, only those lines appear."""
        mock_settings.security_contact = "mailto:security@example.com"
        mock_settings.security_expires = "2025-12-31T23:59:59Z"
        mock_settings.security_encryption = ""
        mock_settings.security_acknowledgments = ""
        mock_settings.security_preferred_languages = ""
        mock_settings.security_canonical = ""
        mock_settings.security_policy = ""
        mock_settings.security_hiring = ""
        mock_settings.security_csaf = ""

        result = generate_security_txt()

        assert "Contact: mailto:security@example.com" in result
        assert "Expires: 2025-12-31T23:59:59Z" in result
        assert len(result.strip().split("\n")) == 2

    @patch("backend.routes.security_txt.settings")
    def test_no_fields_returns_empty_string(self, mock_settings: MagicMock) -> None:
        """When no settings fields are set, the result is an empty string."""
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


class TestSecurityTxtEndpoint:
    """Tests for the /.well-known/security.txt HTTP endpoint."""

    @pytest.fixture
    def _security_app(self):
        """Create a minimal FastAPI app mounting only the security_txt router."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        return app

    @patch("backend.routes.security_txt.settings")
    async def test_endpoint_returns_plain_text_response(
        self, mock_settings: MagicMock, _security_app
    ) -> None:
        """GET /.well-known/security.txt returns 200 with text/plain content."""
        mock_settings.security_contact = "mailto:security@example.com"
        mock_settings.security_expires = "2025-12-31T23:59:59Z"
        mock_settings.security_encryption = ""
        mock_settings.security_acknowledgments = ""
        mock_settings.security_preferred_languages = ""
        mock_settings.security_canonical = ""
        mock_settings.security_policy = ""
        mock_settings.security_hiring = ""
        mock_settings.security_csaf = ""

        transport = ASGITransport(app=_security_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/.well-known/security.txt")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "Contact: mailto:security@example.com" in response.text
        assert "Expires: 2025-12-31T23:59:59Z" in response.text

    @patch("backend.routes.security_txt.settings")
    async def test_endpoint_returns_empty_body_when_no_fields(
        self, mock_settings: MagicMock, _security_app
    ) -> None:
        """GET /.well-known/security.txt returns 200 with empty body when unconfigured."""
        mock_settings.security_contact = ""
        mock_settings.security_expires = ""
        mock_settings.security_encryption = ""
        mock_settings.security_acknowledgments = ""
        mock_settings.security_preferred_languages = ""
        mock_settings.security_canonical = ""
        mock_settings.security_policy = ""
        mock_settings.security_hiring = ""
        mock_settings.security_csaf = ""

        transport = ASGITransport(app=_security_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/.well-known/security.txt")

        assert response.status_code == 200
        assert response.text == ""
