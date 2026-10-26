# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures."""

import os

# Set env vars before any application import: the OAuth2 scheme is built at import time.
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from vpn_portal.auth.models import User
from vpn_portal.main import app


@pytest.fixture
def test_user() -> User:
    """A user holding the standard VPN scopes."""
    return User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=["vpn:connect", "openid", "profile", "email"],
        is_machine_client=False,
        client_id="test-client-id",
    )


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client bound in-process to the ASGI application."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
