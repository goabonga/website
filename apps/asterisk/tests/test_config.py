# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/config.py."""

import importlib

import pytest
from asterisk import __version__
from asterisk import config as config_module


@pytest.fixture
def reload_config(clean_env):
    """Reload the config module so class attributes re-read the environment."""
    yield lambda: importlib.reload(config_module)
    importlib.reload(config_module)


class TestVersion:
    def test_version_is_set(self):
        assert __version__ == "0.0.0"


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

    def test_port_is_int(self):
        assert isinstance(config_module.Config.AUDIOSOCKET_PORT, int)

    def test_module_level_singleton_exists(self):
        assert isinstance(config_module.config, config_module.Config)
