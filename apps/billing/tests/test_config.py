# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/config.py."""

import os
from pathlib import Path
from unittest.mock import patch

from billing.config import Settings, get_credential


def _settings(**overrides) -> Settings:
    """Build Settings ignoring any .env file and keeping secrets explicit."""
    overrides.setdefault("oauth2_client_secret", "")
    with patch.dict(os.environ, {}, clear=False):
        return Settings(_env_file=None, **overrides)


class TestGetCredential:
    """Tests for the get_credential() function."""

    def test_reads_from_credentials_directory(self, tmp_path: Path):
        """Should read credential from systemd CREDENTIALS_DIRECTORY."""
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("secret-value-from-file\n")

        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=False):
            result = get_credential("MY_SECRET", "default")

        assert result == "secret-value-from-file"

    def test_strips_whitespace_from_credential_file(self, tmp_path: Path):
        """Should strip leading/trailing whitespace from credential file content."""
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("  value-with-spaces  \n")

        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=False):
            result = get_credential("MY_SECRET")

        assert result == "value-with-spaces"

    def test_falls_back_to_env_var_when_no_creds_dir(self):
        """Should fall back to environment variable when CREDENTIALS_DIRECTORY is not set."""
        env = {"MY_SECRET": "env-value"}
        # Remove CREDENTIALS_DIRECTORY if present
        env_clean = {k: v for k, v in os.environ.items() if k != "CREDENTIALS_DIRECTORY"}
        env_clean.update(env)

        with patch.dict(os.environ, env_clean, clear=True):
            result = get_credential("MY_SECRET", "default")

        assert result == "env-value"

    def test_falls_back_to_env_var_when_file_not_found(self, tmp_path: Path):
        """Should fall back to env var when credential file does not exist in creds dir."""
        env = {
            "CREDENTIALS_DIRECTORY": str(tmp_path),
            "MY_SECRET": "env-fallback",
        }

        with patch.dict(os.environ, env, clear=False):
            result = get_credential("MY_SECRET", "default")

        assert result == "env-fallback"

    def test_returns_default_when_nothing_found(self):
        """Should return default when neither creds dir nor env var is available."""
        env_clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("CREDENTIALS_DIRECTORY", "NONEXISTENT_KEY")
        }

        with patch.dict(os.environ, env_clean, clear=True):
            result = get_credential("NONEXISTENT_KEY", "my-default")

        assert result == "my-default"

    def test_returns_empty_string_default(self):
        """Should return empty string when no default is specified and nothing found."""
        env_clean = {
            k: v for k, v in os.environ.items() if k not in ("CREDENTIALS_DIRECTORY", "MISSING_KEY")
        }

        with patch.dict(os.environ, env_clean, clear=True):
            result = get_credential("MISSING_KEY")

        assert result == ""

    def test_creds_dir_takes_priority_over_env_var(self, tmp_path: Path):
        """Credential file should take priority over environment variable."""
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("file-value")

        env = {
            "CREDENTIALS_DIRECTORY": str(tmp_path),
            "MY_SECRET": "env-value",
        }

        with patch.dict(os.environ, env, clear=False):
            result = get_credential("MY_SECRET", "default")

        assert result == "file-value"


class TestSettings:
    """Tests for the Settings class."""

    def test_default_values(self):
        """Settings should have sensible defaults."""
        s = _settings()

        assert s.app_name == "Billing API"
        assert s.docs_enabled is False
        assert s.database_echo is False
        assert s.log_level == "INFO"

    def test_default_database_url(self):
        """Settings should have a default database URL."""
        s = _settings()

        assert "postgresql+asyncpg" in s.database_url
        assert "billing" in s.database_url

    def test_default_cors_is_closed(self):
        """No origin should be allowed unless the deployment lists it."""
        s = _settings()

        assert s.cors_origins == []
        assert s.cors_credentials is False
        assert s.cors_methods == ["*"]
        assert s.cors_headers == ["*"]

    def test_database_pool_defaults_and_override(self):
        """The connection pool size should come from the settings."""
        assert _settings().database_pool_size == 10
        assert _settings().database_max_overflow == 20

        s = _settings(database_pool_size=3, database_max_overflow=1)
        assert (s.database_pool_size, s.database_max_overflow) == (3, 1)

    def test_default_redis_url(self):
        """Settings should have a default Redis URL."""
        s = _settings()

        assert s.redis_url.startswith("redis://")

    def test_default_token_cache_ttls(self):
        """Token caching TTLs should have defaults."""
        s = _settings()

        assert s.token_introspection_cache_ttl == 60
        assert s.oauth2_client_cache_ttl == 300

    def test_empty_oauth2_by_default(self):
        """OAuth2 settings should be empty strings by default."""
        s = _settings()

        assert s.oauth2_issuer == ""
        assert s.oauth2_swagger_client_id == ""
        assert s.oauth2_client_id == ""
        assert s.oauth2_client_secret == ""

    def test_oauth2_http_timeout_is_configurable(self):
        """The timeout of the calls to the auth service should be a setting."""
        assert _settings().oauth2_http_timeout == 10.0
        assert _settings(oauth2_http_timeout=2.5).oauth2_http_timeout == 2.5

    def test_settings_from_env_vars(self):
        """Settings should load from environment variables."""
        env = {
            "APP_NAME": "Custom Billing",
            "DOCS_ENABLED": "true",
            "DATABASE_ECHO": "true",
            "LOG_LEVEL": "DEBUG",
        }

        with patch.dict(os.environ, env, clear=False):
            s = Settings(
                _env_file=None,
                oauth2_client_secret="",
            )

        assert s.app_name == "Custom Billing"
        assert s.docs_enabled is True
        assert s.database_echo is True
        assert s.log_level == "DEBUG"
