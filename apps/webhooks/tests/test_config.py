# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for webhooks.config module."""

from unittest.mock import patch

from webhooks.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "Webhooks"
        assert s.log_level == "INFO"
        assert s.docs_enabled is False
        assert s.cors_origins == []
        assert s.cors_credentials is True
        assert s.cors_methods == ["*"]
        assert s.cors_headers == ["*"]

    def test_env_override(self):
        env = {
            "APP_NAME": "custom-webhooks",
            "LOG_LEVEL": "DEBUG",
            "DOCS_ENABLED": "true",
            "CORS_ORIGINS": '["https://a.example","https://b.example"]',
            "CORS_CREDENTIALS": "false",
            "CORS_METHODS": '["GET","POST"]',
            "CORS_HEADERS": '["X-Test"]',
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "custom-webhooks"
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
        assert s.cors_origins == ["https://a.example", "https://b.example"]
        assert s.cors_credentials is False
        assert s.cors_methods == ["GET", "POST"]
        assert s.cors_headers == ["X-Test"]

    def test_env_names_are_case_insensitive(self):
        with patch.dict("os.environ", {"app_name": "lower"}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "lower"
