# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from apt_server.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    """In-process HTTP client bound to the ASGI application."""
    with TestClient(app) as test_client:
        yield test_client
