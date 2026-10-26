# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures for the test suite."""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set OAUTH2_ISSUER before any app import so that the OAuth2 scheme is a
# callable object rather than None.  Python 3.13 + FastAPI raises TypeError
# when inspecting Depends(None) at route-decoration time.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")

from backend.auth.models import User
from backend.main import app


@pytest.fixture
def user_id():
    """Return a fixed user UUID."""
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def session_id():
    """Return a fixed session ID."""
    return "abcdef12-3456-7890-abcd-ef1234567890"


@pytest.fixture
def conversation_id():
    """Return a fixed conversation UUID."""
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def sample_user(user_id):
    """Return a sample authenticated User."""
    return User(
        id=user_id,
        email="test@example.com",
        name="Test User",
        scopes=["openid", "profile", "api:read"],
    )


@pytest.fixture
def sample_jwt_claims(user_id):
    """Return sample JWT claims."""
    return {
        "sub": str(user_id),
        "email": "test@example.com",
        "name": "Test User",
        "scope": "openid profile api:read",
        "iss": "https://auth.example.com",
        "aud": "test-client",
        "exp": 9999999999,
        "iat": 1700000000,
    }


@pytest.fixture
def mock_db_session():
    """Return a mocked AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    """Return a mocked Redis client."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.pipeline = MagicMock()
    r.close = AsyncMock()
    r.aclose = AsyncMock()
    r.zrem = AsyncMock()

    # Pipeline mock
    pipe = AsyncMock()
    pipe.execute = AsyncMock(return_value=[0, 0])
    pipe.zremrangebyscore = MagicMock()
    pipe.zcard = MagicMock()
    pipe.zadd = MagicMock()
    pipe.expire = MagicMock()
    r.pipeline.return_value = pipe

    return r


@pytest.fixture
def sample_conversation():
    """Return a mock Conversation object."""
    conv = MagicMock()
    conv.id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    conv.user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    conv.session_id = None
    conv.title = "Test Conversation"
    conv.summary = "A test conversation summary."
    conv.archived_at = None
    conv.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    conv.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    conv.messages = []
    return conv


@pytest.fixture
def sample_messages():
    """Return sample conversation history."""
    return [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there! How can I help you?"},
    ]


@pytest.fixture
def test_user() -> User:
    """Create a test user with standard API scopes."""
    return User(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        email="test@example.com",
        name="Test User",
        scopes=["openid", "profile", "api:read"],
        is_machine_client=False,
        client_id="test-client-id",
    )


@pytest.fixture
def admin_user() -> User:
    """Create an admin user with wildcard scope."""
    return User(
        id=uuid.uuid4(),
        email="admin@example.com",
        name="Admin User",
        scopes=["api:*"],
        is_machine_client=False,
        client_id="admin-client-id",
    )


@pytest.fixture
def machine_user() -> User:
    """Create a machine client user."""
    return User(
        id="api-service",
        email=None,
        name=None,
        scopes=["api:read"],
        is_machine_client=True,
        client_id="api-service",
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

    jwks_patcher = patch("backend.auth.dependencies.jwks_manager")
    introspection_patcher = patch("backend.auth.dependencies.introspection_client")
    exchange_patcher = patch("backend.auth.dependencies.token_exchange_client")

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
async def auth_client(mock_db_session, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create an authenticated test client with standard user scopes."""
    from backend.database import get_db

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
    from backend.database import get_db

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
