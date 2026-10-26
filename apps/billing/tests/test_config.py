# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/config.py."""

import os
from unittest.mock import patch

from billing.config import Settings


def _settings(**overrides) -> Settings:
    """Build Settings ignoring any .env file and keeping secrets explicit."""
    with patch.dict(os.environ, {}, clear=False):
        return Settings(_env_file=None, **overrides)


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
            )

        assert s.app_name == "Custom Billing"
        assert s.docs_enabled is True
        assert s.database_echo is True
        assert s.log_level == "DEBUG"
