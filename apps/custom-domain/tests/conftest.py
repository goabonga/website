# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from custom_domain.auth.models import User
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


@pytest.fixture
def test_user() -> User:
    """Create a test user with standard scopes."""
    return User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=["custom-domain:read", "custom-domain:write", "custom-domain:lookup"],
        is_machine_client=False,
        client_id="test-client-id",
    )


@pytest.fixture
def admin_user() -> User:
    """Create an admin user with all scopes."""
    return User(
        id=uuid4(),
        email="admin@example.com",
        name="Admin User",
        scopes=[
            "custom-domain:admin",
            "custom-domain:admin:clients",
            "custom-domain:admin:templates",
            "custom-domain:admin:stats",
            "custom-domain:read",
            "custom-domain:write",
            "custom-domain:lookup",
        ],
        is_machine_client=False,
        client_id="admin-client-id",
    )


@pytest.fixture
def machine_user() -> User:
    """Create a machine/service account user."""
    return User(
        id="service-account",
        email=None,
        name=None,
        scopes=["custom-domain:read", "custom-domain:lookup"],
        is_machine_client=True,
        client_id="service-client-id",
    )


@pytest.fixture
def other_user() -> User:
    """Create a user from a different client."""
    return User(
        id=uuid4(),
        email="other@example.com",
        name="Other User",
        scopes=["custom-domain:read", "custom-domain:write", "custom-domain:lookup"],
        is_machine_client=False,
        client_id="other-client-id",
    )


def _create_jwt_claims(user: User) -> dict:
    """Create JWT claims from a User object."""
    return {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "scope": " ".join(user.scopes) if user.scopes else "",
        "client_id": user.client_id,
    }


def _setup_auth_mocks(user: User):
    """Set up authentication mocks for a given user."""
    claims = _create_jwt_claims(user)

    jwks_patcher = patch("custom_domain.auth.dependencies.jwks_manager")
    introspection_patcher = patch("custom_domain.auth.dependencies.introspection_client")
    exchange_patcher = patch("custom_domain.auth.dependencies.token_exchange_client")

    mock_jwks = jwks_patcher.start()
    mock_introspection = introspection_patcher.start()
    mock_exchange = exchange_patcher.start()

    mock_jwks.is_configured = True
    mock_jwks.validate_token = AsyncMock(return_value=claims)

    mock_introspection.validate_token_with_introspection = AsyncMock(return_value=claims)
    mock_introspection.validate_opaque_token = AsyncMock(return_value=claims)

    mock_exchange.is_configured = False

    return jwks_patcher, introspection_patcher, exchange_patcher


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


@pytest_asyncio.fixture
async def auth_client(mock_db_session, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with authenticated user."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    patchers = _setup_auth_mocks(test_user)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as test_client:
            yield test_client
    finally:
        for p in patchers:
            p.stop()
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client_other(mock_db_session, other_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with user from different client."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    patchers = _setup_auth_mocks(other_user)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as test_client:
            yield test_client
    finally:
        for p in patchers:
            p.stop()
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(mock_db_session, admin_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with admin user."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    patchers = _setup_auth_mocks(admin_user)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as test_client:
            yield test_client
    finally:
        for p in patchers:
            p.stop()
        app.dependency_overrides.clear()


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    mock.setex = AsyncMock()
    mock.delete = AsyncMock()
    mock.lrange = AsyncMock(return_value=[])
    mock.llen = AsyncMock(return_value=0)
    mock.lpush = AsyncMock()
    mock.close = AsyncMock()
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def mock_httpx():
    """Mock httpx client for external API calls."""
    with patch("httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock.return_value.__aexit__ = AsyncMock()
        yield client_instance
