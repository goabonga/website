# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.config module."""

from mailler.config import Settings


class TestSettingsDefaults:
    """Default values of the application settings."""

    def test_application_defaults(self):
        s = Settings(_env_file=None)
        assert s.app_name == "Mailler API"
        assert s.log_level == "INFO"
        assert s.docs_enabled is False
        assert s.database_echo is False

    def test_database_default(self):
        assert Settings(_env_file=None).database_url == "postgresql:///mailler"

    def test_cors_defaults(self):
        s = Settings(_env_file=None)
        assert s.cors_origins == []
        assert s.cors_credentials is True
        assert s.cors_methods == ["*"]
        assert s.cors_headers == ["*"]


class TestSettingsFromEnvironment:
    """Settings are read from environment variables."""

    def test_environment_overrides_default(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("DOCS_ENABLED", "true")
        monkeypatch.setenv("CORS_ORIGINS", '["https://example.test"]')
        s = Settings(_env_file=None)
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
        assert s.cors_origins == ["https://example.test"]

    def test_unknown_variables_are_ignored(self, monkeypatch):
        monkeypatch.setenv("SOMETHING_UNKNOWN", "x")
        assert not hasattr(Settings(_env_file=None), "something_unknown")
