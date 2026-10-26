# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Test configuration and fixtures. Pure mocks, no real infrastructure."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge.auth.dependencies import AuthContext, get_auth_context
from knowledge.auth.models import User
from knowledge.database import get_db
from knowledge.main import app

# ============================================================
# Fixed IDs
# ============================================================

TEST_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_TENANT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


# ============================================================
# Mock DB fixture
# ============================================================


def _make_result(scalar_one_or_none=None, scalar=0, scalars_all=None, rowcount=0):
    """Create a mock SQLAlchemy Result object with sync methods."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    result.all.return_value = []
    result.rowcount = rowcount
    return result


@pytest.fixture
def mock_db():
    """Mock AsyncSession. No real database."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_make_result())
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ============================================================
# Mock Auth
# ============================================================


def _make_auth_context() -> AuthContext:
    """Create a mock AuthContext with all scopes."""
    user = User(
        id=TEST_USER_ID,
        email="test@example.com",
        name="Test User",
        scopes=[
            "collections:read",
            "collections:write",
            "collections:search",
            "documents:read",
            "documents:write",
        ],
    )
    return AuthContext(user=user, tenant_id=TEST_TENANT_ID)


# ============================================================
# Test client (mock DB + mock auth)
# ============================================================


@pytest.fixture
async def client(mock_db) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with mocked DB and auth."""

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_auth_context] = _make_auth_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
