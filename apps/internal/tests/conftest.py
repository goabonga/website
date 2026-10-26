# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx

# ---------------------------------------------------------------------------
# Fix oauth2_scheme for Python 3.13 compatibility
# ---------------------------------------------------------------------------
# When settings.oauth2_issuer is empty, _get_oauth2_scheme() returns None
# and Depends(None) causes inspect.signature to fail on Python 3.13 with
# ``TypeError: str | None is not a callable object``.
# Patching it with a no-op async function before any route module is imported
# so that FastAPI can introspect the dependency chain.
import internal.auth.dependencies as _deps  # noqa: E402
import pytest

if _deps.oauth2_scheme is None:

    async def _fake_oauth2_scheme() -> str | None:  # type: ignore[return]
        return None

    _deps.oauth2_scheme = _fake_oauth2_scheme  # type: ignore[assignment]

from internal.auth.models import User


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def mock_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="test@example.com",
        name="Test User",
        scopes=["knowledge:read", "knowledge:write", "prompts:read"],
    )


@pytest.fixture
def mock_admin_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="admin@example.com",
        name="Admin User",
        scopes=["*"],
    )


@pytest.fixture
def mock_settings():
    """Patched settings for tests."""
    with patch("internal.config.settings") as s:
        s.oauth2_issuer = "https://auth.example.com"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.mailler_api_url = "https://mailler.example.com"
        s.mailler_socket_path = ""
        s.redis_url = "redis://localhost:6379/0"
        s.openai_api_key = "sk-test-key"
        s.vpn_portal_api_url = "https://vpn.example.com"
        s.oauth2_client_cache_ttl = 300
        s.debug = False
        s.database_url = "postgresql://test:test@localhost/testdb"
        yield s


def make_httpx_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
    text: str = "",
) -> httpx.Response:
    """Factory for creating mock httpx.Response objects."""
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "https://example.com"),
        json=json_data,
        text=text if not json_data else "",
    )


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient as async context manager."""
    mock_client = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm, mock_client
