# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared fixtures for API v1 tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from auth.main import app as fastapi_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True

    # Primary email
    email = MagicMock()
    email.email = "test@example.com"
    email.is_primary = True
    email.is_verified = True
    user.emails = [email]

    # Profile
    profile = MagicMock()
    profile.nickname = "testuser"
    profile.name = "Test User"
    profile.given_name = "Test"
    profile.family_name = "User"
    profile.middle_name = None
    profile.preferred_username = "testuser"
    profile.picture_url = None
    profile.website = None
    profile.gender = None
    profile.birthdate = None
    profile.zoneinfo = None
    profile.locale = None
    profile.phone_number = None
    user.profile = profile

    return user


@pytest.fixture
def mock_db():
    """Create a mocked async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def app(mock_user):
    """Create test app with mocked auth."""

    async def override_auth():
        return mock_user

    fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth

    yield fastapi_app

    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
