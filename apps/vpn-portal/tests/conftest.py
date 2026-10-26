# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures."""

import os

# Set env vars before any application import: the OAuth2 scheme is built at import time.
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")

from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
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


def claims_for(user: User) -> dict:
    """JWT claims matching a User."""
    return {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "scope": " ".join(user.scopes),
        "client_id": user.client_id,
    }


@contextmanager
def authenticated_as(user: User) -> Iterator[None]:
    """Make the auth dependencies accept any bearer token as ``user``.

    JWKS validation, introspection and token exchange are replaced, the real
    ``require_scopes`` dependency still checks the scopes of ``user``.
    """
    claims = claims_for(user)
    with (
        patch("vpn_portal.auth.dependencies.jwks_manager") as jwks,
        patch("vpn_portal.auth.dependencies.introspection_client") as introspection,
        patch("vpn_portal.auth.dependencies.token_exchange_client") as exchange,
    ):
        jwks.is_configured = True
        introspection.validate_token_with_introspection = AsyncMock(return_value=claims)
        introspection.validate_opaque_token = AsyncMock(return_value=claims)
        exchange.is_configured = False
        yield


@pytest_asyncio.fixture
async def auth_client(test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a user holding ``vpn:connect``."""
    with authenticated_as(test_user):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as test_client:
            yield test_client
