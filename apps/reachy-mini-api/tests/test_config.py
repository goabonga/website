# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the foundation settings."""

import os
from unittest.mock import patch

from reachy_mini_api.config import Settings, get_credential


class TestGetCredential:
    """Tests for get_credential."""

    def test_returns_default_when_no_env(self):
        """Return the default value when no environment variable is set."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_credential("NONEXISTENT_VAR", "default_val") == "default_val"

    def test_returns_env_var_when_set(self):
        """Return the environment variable value when set."""
        with patch.dict(os.environ, {"MY_SECRET": "env_value"}, clear=True):
            assert get_credential("MY_SECRET", "default") == "env_value"

    def test_returns_empty_string_default(self):
        """Return an empty string when no default is given."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_credential("MISSING") == ""

    def test_reads_from_credentials_directory(self, tmp_path):
        """Read the credential from the systemd credentials directory."""
        (tmp_path / "MY_CRED").write_text("  cred_value  \n")
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=True):
            assert get_credential("MY_CRED", "default") == "cred_value"

    def test_credentials_directory_file_not_found(self, tmp_path):
        """Fall back to the environment when the credential file does not exist."""
        env = {"CREDENTIALS_DIRECTORY": str(tmp_path), "MISSING_CRED": "env_val"}
        with patch.dict(os.environ, env, clear=True):
            assert get_credential("MISSING_CRED", "default") == "env_val"


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
        assert s.oauth2_client_id == ""
        assert s.redis_url == ""
        assert s.redis_key_prefix == "reachy"
        assert s.token_introspection_cache_ttl == 60

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
            "OAUTH2_CLIENT_ID": "reachy-api",
            "REDIS_URL": "redis://localhost:6379/5",
            "REDIS_KEY_PREFIX": "custom",
            "TOKEN_INTROSPECTION_CACHE_TTL": "10",
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
        assert s.oauth2_client_id == "reachy-api"
        assert s.redis_url == "redis://localhost:6379/5"
        assert s.redis_key_prefix == "custom"
        assert s.token_introspection_cache_ttl == 10

    def test_settings_from_env_file(self, tmp_path):
        """Load settings from a .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("APP_NAME=From File\n")
        with patch.dict(os.environ, {}, clear=True):
            s = Settings(_env_file=env_file)
        assert s.app_name == "From File"

    def test_client_secret_from_env(self):
        """The client secret is read from the environment."""
        with patch.dict(os.environ, {"OAUTH2_CLIENT_SECRET": "s3cret"}, clear=True):
            s = Settings(_env_file=None)
        assert s.oauth2_client_secret == "s3cret"
