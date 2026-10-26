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
