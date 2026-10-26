# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for knowledge/config.py (credential lookup and settings defaults)."""

import os
from unittest.mock import patch

from knowledge.config import get_credential


class TestGetCredential:
    """Test the get_credential helper function."""

    def test_reads_from_credentials_directory(self, tmp_path):
        """When CREDENTIALS_DIRECTORY is set and the file exists, read from it."""
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("  secret-value-from-file  \n")

        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=False):
            result = get_credential("MY_SECRET", "default")

        assert result == "secret-value-from-file"

    def test_falls_back_to_env_when_file_missing(self, tmp_path):
        """When CREDENTIALS_DIRECTORY is set but file does not exist, fall back to env."""
        with patch.dict(
            os.environ,
            {"CREDENTIALS_DIRECTORY": str(tmp_path), "MY_SECRET": "env-value"},
            clear=False,
        ):
            result = get_credential("MY_SECRET", "default")

        assert result == "env-value"

    def test_falls_back_to_env_when_no_creds_dir(self):
        """When CREDENTIALS_DIRECTORY is not set, fall back to env variable."""
        env = {"MY_SECRET": "env-value"}
        with patch.dict(os.environ, env, clear=False):
            # Make sure CREDENTIALS_DIRECTORY is not in env
            os.environ.pop("CREDENTIALS_DIRECTORY", None)
            result = get_credential("MY_SECRET", "default")

        assert result == "env-value"

    def test_falls_back_to_default(self):
        """When neither CREDENTIALS_DIRECTORY nor env var is set, return default."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_credential("NONEXISTENT_SECRET", "my-default")

        assert result == "my-default"

    def test_empty_default(self):
        """Default is empty string when not provided."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_credential("NONEXISTENT_SECRET")

        assert result == ""


class TestSettingsDefaults:
    """Test the default values of the core settings."""

    def test_defaults(self):
        from knowledge.config import Settings

        settings = Settings(_env_file=None)
        assert settings.app_name == "Knowledge API"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.docs_enabled is False
        assert settings.cors_origins == ["*"]

    def test_environment_overrides_defaults(self):
        from knowledge.config import Settings

        with patch.dict(os.environ, {"APP_NAME": "Custom", "DOCS_ENABLED": "true"}):
            settings = Settings(_env_file=None)
        assert settings.app_name == "Custom"
        assert settings.docs_enabled is True

    def test_get_settings_is_cached(self):
        from knowledge.config import get_settings

        assert get_settings() is get_settings()
