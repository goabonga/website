# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Test configuration and fixtures. Pure mocks, no real infrastructure."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create an HTTP client bound to the ASGI application."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
