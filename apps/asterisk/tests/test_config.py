# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/config.py."""

import importlib

import pytest
from asterisk import __version__
from asterisk import config as config_module
from asterisk.config import get_credential


@pytest.fixture
def reload_config(clean_env):
    """Reload the config module so class attributes re-read the environment."""
    yield lambda: importlib.reload(config_module)
    importlib.reload(config_module)


class TestVersion:
    def test_version_is_set(self):
        assert __version__ == "0.0.0"


class TestGetCredential:
    def test_returns_default_when_no_env_and_no_creds_dir(self, monkeypatch):
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.delenv("MY_SECRET", raising=False)
        assert get_credential("MY_SECRET", "default-val") == "default-val"

    def test_returns_env_value_when_no_creds_dir(self, monkeypatch):
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.setenv("MY_SECRET", "sk-from-env")
        assert get_credential("MY_SECRET") == "sk-from-env"

    def test_returns_credential_file_content(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("sk-from-file\n")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        assert get_credential("MY_SECRET") == "sk-from-file"

    def test_credential_file_strips_whitespace(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("  sk-padded  \n")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        assert get_credential("MY_SECRET") == "sk-padded"

    def test_falls_back_to_env_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("MY_SECRET", "sk-from-env")
        assert get_credential("MY_SECRET") == "sk-from-env"

    def test_returns_custom_default(self, monkeypatch):
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.delenv("NONEXISTENT", raising=False)
        assert get_credential("NONEXISTENT", "my-default") == "my-default"

    def test_returns_empty_string_default(self, monkeypatch):
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.delenv("NONEXISTENT", raising=False)
        assert get_credential("NONEXISTENT") == ""


class TestConfig:
    def test_defaults(self, reload_config):
        module = reload_config()
        assert module.Config.AUDIOSOCKET_HOST == "127.0.0.1"
        assert module.Config.AUDIOSOCKET_PORT == 9092
        assert module.Config.LOG_LEVEL == "INFO"

    def test_environment_overrides(self, reload_config, monkeypatch):
        monkeypatch.setenv("AUDIOSOCKET_HOST", "0.0.0.0")
        monkeypatch.setenv("AUDIOSOCKET_PORT", "4000")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        module = reload_config()
        assert module.Config.AUDIOSOCKET_HOST == "0.0.0.0"
        assert module.Config.AUDIOSOCKET_PORT == 4000
        assert module.Config.LOG_LEVEL == "DEBUG"

    def test_openai_defaults(self, reload_config):
        module = reload_config()
        assert module.Config.OPENAI_API_KEY == ""
        assert module.Config.OPENAI_MODEL == "gpt-4o-realtime-preview-2024-12-17"
        assert module.Config.OPENAI_VOICE == "alloy"
        assert "phone assistant" in module.Config.OPENAI_SYSTEM_PROMPT

    def test_openai_environment_overrides(self, reload_config, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        monkeypatch.setenv("OPENAI_MODEL", "other-model")
        monkeypatch.setenv("OPENAI_VOICE", "verse")
        monkeypatch.setenv("OPENAI_SYSTEM_PROMPT", "Be brief.")
        module = reload_config()
        assert module.Config.OPENAI_API_KEY == "sk-env"
        assert module.Config.OPENAI_MODEL == "other-model"
        assert module.Config.OPENAI_VOICE == "verse"
        assert module.Config.OPENAI_SYSTEM_PROMPT == "Be brief."

    def test_api_key_comes_from_systemd_credentials(self, reload_config, mock_credentials_dir):
        module = reload_config()
        assert module.Config.OPENAI_API_KEY == "sk-test-from-creds"

    def test_port_is_int(self):
        assert isinstance(config_module.Config.AUDIOSOCKET_PORT, int)

    def test_module_level_singleton_exists(self):
        assert isinstance(config_module.config, config_module.Config)
