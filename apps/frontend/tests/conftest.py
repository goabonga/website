# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from frontend.config import Settings
from frontend.main import create_app

SettingsFactory = Callable[..., Settings]


@pytest.fixture
def make_settings() -> SettingsFactory:
    """Build settings that ignore any local .env file."""

    def factory(**overrides) -> Settings:
        return Settings(_env_file=None, **overrides)

    return factory


@pytest.fixture
def client(make_settings: SettingsFactory) -> TestClient:
    return TestClient(create_app(make_settings()))
