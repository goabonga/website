# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from team.auth.models import User
from team.database import get_db
from team.main import app


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock()
    session.close = AsyncMock()

    async def _mock_refresh(obj, *args, **kwargs):
        """Simulate db.refresh() by populating auto-generated fields."""
        now = datetime.now(UTC)
        for attr, default in [
            ("id", str(uuid4())),
            ("is_active", True),
            ("created_at", now),
            ("updated_at", now),
            ("output_data", {}),
        ]:
            try:
                if getattr(obj, attr, "SKIP") is None:
                    setattr(obj, attr, default)
            except Exception:
                pass

    session.refresh = AsyncMock(side_effect=_mock_refresh)
    return session


@pytest.fixture
def test_user() -> User:
    """Create a test user with standard team scopes."""
    return User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=[
            "team:platform:read",
            "team:platform:write",
            "team:read",
            "team:write",
        ],
        is_machine_client=False,
        client_id="test-client-id",
    )


@pytest.fixture
def admin_user() -> User:
    """Create an admin user with wildcard team scope."""
    return User(
        id=uuid4(),
        email="admin@example.com",
        name="Admin User",
        scopes=["team:*"],
        is_machine_client=False,
        client_id="admin-client-id",
    )


@pytest.fixture
def machine_user() -> User:
    """Create a machine client user."""
    return User(
        id="team-service",
        email=None,
        name=None,
        scopes=["team:platform:read", "team:write"],
        is_machine_client=True,
        client_id="team-service",
    )


def _create_jwt_claims(user: User) -> dict:
    """Create JWT claims dict from a User instance."""
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

    jwks_patcher = patch("team.auth.dependencies.jwks_manager")
    introspection_patcher = patch("team.auth.dependencies.introspection_client")
    exchange_patcher = patch("team.auth.dependencies.token_exchange_client")

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
    """Create an unauthenticated test client."""

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
    """Create an authenticated test client with standard user scopes."""

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
async def admin_client(mock_db_session, admin_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create an authenticated test client with admin (wildcard) scopes."""

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
def sample_team_data():
    """Sample team data for testing."""
    return {
        "name": "Engineering",
        "slug": "engineering",
        "description": "Engineering team",
        "config": {},
    }
