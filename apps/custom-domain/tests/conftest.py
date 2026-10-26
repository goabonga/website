# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from custom_domain.database import get_db
from custom_domain.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest_asyncio.fixture
async def client(mock_db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with mocked database (no auth)."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
