# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures."""

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all app-relevant env vars so Config picks up only test-set values."""
    env_vars = [
        "AUDIOSOCKET_HOST",
        "AUDIOSOCKET_PORT",
        "LOG_LEVEL",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
