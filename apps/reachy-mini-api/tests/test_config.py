# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the foundation settings."""

import os
from unittest.mock import patch

from reachy_mini_api.config import Settings


class TestSettings:
    """Tests for the Settings class."""

    def test_default_values(self):
        """Verify default settings values."""
        with patch.dict(os.environ, {}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "Reachy Mini API"
        assert s.debug is False
        assert s.log_level == "INFO"
        assert s.docs_enabled is False
        assert s.cors_origins == ["*"]
        assert s.cors_credentials is True
        assert s.cors_methods == ["GET", "POST"]
        assert s.cors_headers == ["*"]
        assert s.oauth2_issuer == ""
        assert s.oauth2_swagger_client_id == ""
        assert s.oauth2_trusted_issuers == ""
        assert s.jwks_cache_ttl == 3600

    def test_settings_from_env(self):
        """Load settings from environment variables."""
        env = {
            "APP_NAME": "Custom API",
            "DEBUG": "true",
            "LOG_LEVEL": "DEBUG",
            "DOCS_ENABLED": "true",
            "CORS_ORIGINS": '["https://reachy.internal"]',
            "CORS_CREDENTIALS": "false",
            "OAUTH2_ISSUER": "https://auth.test.com",
            "OAUTH2_SWAGGER_CLIENT_ID": "swagger",
            "OAUTH2_TRUSTED_ISSUERS": "https://other.test.com",
            "JWKS_CACHE_TTL": "60",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "Custom API"
        assert s.debug is True
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
        assert s.cors_origins == ["https://reachy.internal"]
        assert s.cors_credentials is False
        assert s.oauth2_issuer == "https://auth.test.com"
        assert s.oauth2_swagger_client_id == "swagger"
        assert s.oauth2_trusted_issuers == "https://other.test.com"
        assert s.jwks_cache_ttl == 60

    def test_settings_from_env_file(self, tmp_path):
        """Load settings from a .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("APP_NAME=From File\n")
        with patch.dict(os.environ, {}, clear=True):
            s = Settings(_env_file=env_file)
        assert s.app_name == "From File"
