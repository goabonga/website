# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.config module."""

from unittest.mock import patch

from analytics.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "Analytics"
        assert s.log_level == "INFO"
        assert s.docs_enabled is False

    def test_cors_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.cors_origins == ["*"]
        assert s.cors_credentials is True
        assert s.cors_methods == ["GET", "POST", "OPTIONS"]
        assert s.cors_headers == ["*"]

    def test_env_override(self):
        env = {
            "APP_NAME": "CustomApp",
            "LOG_LEVEL": "DEBUG",
            "DOCS_ENABLED": "true",
            "CORS_ORIGINS": '["https://example.com"]',
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "CustomApp"
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
        assert s.cors_origins == ["https://example.com"]

    def test_env_is_case_insensitive(self):
        with patch.dict("os.environ", {"app_name": "lower"}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "lower"

    def test_security_txt_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.security_contact == ""
        assert s.security_expires == ""
        assert s.security_encryption == ""
        assert s.security_csaf == ""

    def test_security_txt_env_override(self):
        env = {
            "SECURITY_CONTACT": "mailto:security@example.com",
            "SECURITY_POLICY": "https://example.com/policy",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.security_contact == "mailto:security@example.com"
        assert s.security_policy == "https://example.com/policy"

    def test_database_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.database_url == "postgresql://localhost:5432/analytics"
        assert s.database_echo is False
        assert s.data_retention_days == 395

    def test_database_env_override(self):
        env = {
            "DATABASE_URL": "postgresql:///analytics",
            "DATABASE_ECHO": "true",
            "DATA_RETENTION_DAYS": "30",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.database_url == "postgresql:///analytics"
        assert s.database_echo is True
        assert s.data_retention_days == 30
