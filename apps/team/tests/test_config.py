# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/config.py."""

import os
from pathlib import Path
from unittest.mock import patch

from team.config import Settings, get_credential


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
        with patch.dict(os.environ, {}, clear=False):
            s = Settings(
                _env_file=None,
                openai_api_key="",
                oauth2_client_secret="",
            )

        assert s.app_name == "Team"
        assert s.docs_enabled is True
        assert s.database_echo is False
        assert s.log_level == "INFO"
        assert s.oauth2_token_cache_ttl == 300
        assert s.oauth2_introspection_cache_ttl == 60

    def test_default_database_url(self):
        """Settings should have a default database URL."""
        with patch.dict(os.environ, {}, clear=False):
            s = Settings(
                _env_file=None,
                openai_api_key="",
                oauth2_client_secret="",
            )

        assert "postgresql+asyncpg" in s.database_url
        assert "team" in s.database_url

    def test_default_redis_url(self):
        """Settings should have a default Redis URL."""
        with patch.dict(os.environ, {}, clear=False):
            s = Settings(
                _env_file=None,
                openai_api_key="",
                oauth2_client_secret="",
            )

        assert s.redis_url.startswith("redis://")

    def test_empty_oauth2_by_default(self):
        """OAuth2 settings should be empty strings by default."""
        with patch.dict(os.environ, {}, clear=False):
            s = Settings(
                _env_file=None,
                openai_api_key="",
                oauth2_client_secret="",
            )

        assert s.oauth2_issuer == ""
        assert s.oauth2_swagger_client_id == ""
        assert s.oauth2_client_id == ""
        assert s.oauth2_client_secret == ""

    def test_settings_from_env_vars(self):
        """Settings should load from environment variables."""
        env = {
            "APP_NAME": "Custom Team",
            "DOCS_ENABLED": "true",
            "DATABASE_ECHO": "true",
            "LOG_LEVEL": "DEBUG",
            "OPENAI_API_KEY": "sk-test-123",
        }

        with patch.dict(os.environ, env, clear=False):
            s = Settings(
                _env_file=None,
                openai_api_key="sk-test-123",
                oauth2_client_secret="",
            )

        assert s.app_name == "Custom Team"
        assert s.docs_enabled is True
        assert s.database_echo is True
        assert s.log_level == "DEBUG"
        assert s.openai_api_key == "sk-test-123"
