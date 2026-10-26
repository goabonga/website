# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.config module."""

from backend.config import Settings


class TestSettingsDefaults:
    """Tests for Settings default values."""

    def test_application_defaults(self, monkeypatch):
        """Application settings have sensible defaults."""
        for name in ("APP_NAME", "DEBUG", "LOG_LEVEL", "DOCS_ENABLED"):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.app_name == "GOABONGA API"
        assert s.debug is False
        assert s.log_level == "INFO"
        assert s.docs_enabled is False

    def test_cors_defaults_are_permissive(self, monkeypatch):
        """CORS defaults allow every origin, method and header."""
        for name in ("CORS_ORIGINS", "CORS_CREDENTIALS", "CORS_METHODS", "CORS_HEADERS"):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.cors_origins == ["*"]
        assert s.cors_credentials is True
        assert s.cors_methods == ["*"]
        assert s.cors_headers == ["*"]

    def test_database_url_default(self, monkeypatch):
        """DATABASE_URL defaults to a local PostgreSQL database."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert Settings(_env_file=None).database_url == "postgresql://localhost/app"

    def test_values_come_from_environment(self, monkeypatch):
        """Environment variables override defaults, case-insensitively."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("docs_enabled", "true")
        s = Settings(_env_file=None)
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
