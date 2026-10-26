# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for vpn_portal.config."""

import pytest
from vpn_portal.config import Settings

MANAGED = ("APP_NAME", "DEBUG", "DOCS_ENABLED", "LOG_LEVEL")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in MANAGED:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    settings = Settings(_env_file=None)

    assert settings.app_name == "VPN Portal"
    assert settings.debug is False
    assert settings.docs_enabled is True
    assert settings.log_level == "INFO"


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Portal")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DOCS_ENABLED", "false")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Portal"
    assert settings.debug is True
    assert settings.docs_enabled is False
    assert settings.log_level == "DEBUG"


def test_env_file_is_read(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=From File\nLOG_LEVEL=WARNING\n")

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "From File"
    assert settings.log_level == "WARNING"


def test_environment_wins_over_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=WARNING\n")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    assert Settings(_env_file=env_file).log_level == "ERROR"
