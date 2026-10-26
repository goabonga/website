# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run in-process: the FastAPI application is driven through the
Starlette test client, and every external dependency is replaced by a fake
or a patch. No database or Redis server is needed.
"""

import os
from unittest.mock import AsyncMock, MagicMock

from backend.main import app  # noqa: E402

os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")

from starlette.testclient import TestClient  # noqa: E402


def _mock_db_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


def before_scenario(context, scenario):
    """Create a fresh client and an empty patch registry."""
    context.app = app
    context.patches = {}
    context.db = _mock_db_session()
    context.client = TestClient(app, raise_server_exceptions=False)


def after_scenario(context, scenario):
    """Undo overrides, stop patches and close the client."""
    context.app.dependency_overrides.clear()
    for patcher in context.patches.values():
        patcher.stop()
    context.patches.clear()
    context.client.close()
