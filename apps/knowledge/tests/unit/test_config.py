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


class TestGetSettingsCredentials:
    """Secrets are read from systemd credentials or the environment."""

    def _settings(self, env, clear=False):
        from knowledge.config import get_settings

        with patch.dict(os.environ, env, clear=clear):
            return get_settings.__wrapped__()

    def test_secret_comes_from_credentials_directory(self, tmp_path):
        (tmp_path / "OAUTH2_CLIENT_SECRET").write_text("from-credential\n")

        settings = self._settings({"CREDENTIALS_DIRECTORY": str(tmp_path)})

        assert settings.oauth2_client_secret == "from-credential"

    def test_secret_comes_from_environment(self):
        settings = self._settings({"OAUTH2_CLIENT_SECRET": "from-env"})

        assert settings.oauth2_client_secret == "from-env"

    def test_missing_secret_leaves_the_default(self):
        settings = self._settings({}, clear=True)

        assert settings.oauth2_client_secret == ""

    def test_env_file_value_is_not_overwritten_by_an_empty_credential(self, tmp_path, monkeypatch):
        from knowledge.config import get_settings

        (tmp_path / ".env").write_text("OAUTH2_CLIENT_SECRET=from-dotenv\n")
        monkeypatch.chdir(tmp_path)
        for name in ("OAUTH2_CLIENT_SECRET", "CREDENTIALS_DIRECTORY"):
            monkeypatch.delenv(name, raising=False)

        assert get_settings.__wrapped__().oauth2_client_secret == "from-dotenv"

    def test_environment_takes_precedence_over_env_file(self, tmp_path, monkeypatch):
        from knowledge.config import get_settings

        (tmp_path / ".env").write_text("OAUTH2_CLIENT_SECRET=from-dotenv\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("OAUTH2_CLIENT_SECRET", "from-environment")

        assert get_settings.__wrapped__().oauth2_client_secret == "from-environment"
