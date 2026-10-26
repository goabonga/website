# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Settings are read from E2E_* environment variables."""

from pathlib import Path

import pytest
from e2e_support.settings import E2ESettings, SettingsError


def test_defaults():
    settings = E2ESettings.from_env({})
    assert settings.browser == "chromium"
    assert settings.headless is True
    assert settings.slowmo == 0
    assert settings.artifacts_dir == Path("artifacts")
    assert settings.skip_browser is False
    assert settings.trace is True
    assert settings.timeout == 10_000


def test_every_variable_is_read():
    settings = E2ESettings.from_env(
        {
            "E2E_BROWSER": "Firefox",
            "E2E_HEADLESS": "0",
            "E2E_SLOWMO": "250",
            "E2E_ARTIFACTS_DIR": "/tmp/out",
            "E2E_SKIP_BROWSER": "1",
            "E2E_TIMEOUT": "2000",
            "E2E_TRACE": "off",
        }
    )
    assert settings.browser == "firefox"
    assert settings.headless is False
    assert settings.slowmo == 250
    assert settings.artifacts_dir == Path("/tmp/out")
    assert settings.skip_browser is True
    assert settings.timeout == 2000
    assert settings.trace is False


def test_the_process_environment_is_the_default_source(monkeypatch):
    monkeypatch.setenv("E2E_SLOWMO", "7")
    assert E2ESettings.from_env().slowmo == 7


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_truthy_spellings(value):
    assert E2ESettings.from_env({"E2E_SKIP_BROWSER": value}).skip_browser is True


@pytest.mark.parametrize("value", ["0", "false", "No", "off", ""])
def test_falsy_spellings(value):
    assert E2ESettings.from_env({"E2E_HEADLESS": value}).headless is False


def test_a_blank_artifacts_dir_falls_back_to_the_default():
    assert E2ESettings.from_env({"E2E_ARTIFACTS_DIR": " "}).artifacts_dir == Path("artifacts")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("E2E_BROWSER", "netscape"),
        ("E2E_HEADLESS", "maybe"),
        ("E2E_SLOWMO", "fast"),
        ("E2E_SLOWMO", "-5"),
        ("E2E_TIMEOUT", "0"),
    ],
)
def test_invalid_values_are_rejected_with_the_variable_name(name, value):
    with pytest.raises(SettingsError, match=name):
        E2ESettings.from_env({name: value})
