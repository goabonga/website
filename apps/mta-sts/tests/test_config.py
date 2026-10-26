# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mta_sts.config module."""

from unittest.mock import patch

from mta_sts.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "mta-sts"
        assert s.log_level == "INFO"

    def test_env_override(self):
        env = {"APP_NAME": "custom-name", "LOG_LEVEL": "DEBUG"}
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "custom-name"
        assert s.log_level == "DEBUG"


class TestMtaStsSettings:
    """Tests for the MTA-STS policy settings."""

    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.mta_sts_mode == "enforce"
        assert s.mta_sts_mx == "mail.goabonga.com"
        assert s.mta_sts_max_age == 86400

    def test_env_override(self):
        env = {
            "MTA_STS_MODE": "testing",
            "MTA_STS_MX": "mx1.example.com",
            "MTA_STS_MAX_AGE": "3600",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.mta_sts_mode == "testing"
        assert s.mta_sts_mx == "mx1.example.com"
        assert s.mta_sts_max_age == 3600

    def test_mx_hosts_single(self):
        with patch.dict("os.environ", {"MTA_STS_MX": "mail.example.com"}, clear=True):
            s = Settings(_env_file=None)
        assert s.mx_hosts == ["mail.example.com"]

    def test_mx_hosts_multiple(self):
        with patch.dict(
            "os.environ", {"MTA_STS_MX": "mx1.example.com, mx2.example.com"}, clear=True
        ):
            s = Settings(_env_file=None)
        assert s.mx_hosts == ["mx1.example.com", "mx2.example.com"]

    def test_mx_hosts_strips_whitespace(self):
        with patch.dict(
            "os.environ", {"MTA_STS_MX": "  mx1.example.com ,  mx2.example.com  "}, clear=True
        ):
            s = Settings(_env_file=None)
        assert s.mx_hosts == ["mx1.example.com", "mx2.example.com"]

    def test_mx_hosts_ignores_empty_entries(self):
        with patch.dict("os.environ", {"MTA_STS_MX": "mx1.example.com,,, "}, clear=True):
            s = Settings(_env_file=None)
        assert s.mx_hosts == ["mx1.example.com"]
