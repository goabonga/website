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
