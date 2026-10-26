# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.session.dependencies — session management dependencies."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.session.dependencies import (
    ChatContext,
    _validate_session_id,
    get_chat_context,
    require_session_or_auth,
)
from fastapi import HTTPException

# --- Fixtures ---

FIXED_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
VALID_SESSION_ID = "abcdef12-3456-7890-abcd-ef1234567890"


@pytest.fixture
def mock_request():
    """Return a minimal mock Request with client IP."""
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "192.168.1.100"
    return request


@pytest.fixture
def mock_user():
    """Return a sample authenticated User."""
    from backend.auth.models import User

    return User(
        id=FIXED_UUID,
        email="test@example.com",
        name="Test User",
        scopes=["openid", "profile", "api:read"],
    )


@pytest.fixture
def mock_db():
    """Return a mocked AsyncSession."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_rate_limiter():
    """Return a mocked RateLimiter."""
    limiter = AsyncMock()
    limiter.check_session_creation_limit = AsyncMock(return_value=(True, 5, 3600))
    limiter.record_session_creation = AsyncMock()
    return limiter


@pytest.fixture
def mock_session_service():
    """Return a mocked SessionService instance."""
    service = AsyncMock()
    service.get = AsyncMock(return_value=None)
    service.create = AsyncMock()
    service.close = AsyncMock()
    return service


# --- _validate_session_id ---


class TestValidateSessionId:
    """Tests for _validate_session_id helper."""

    def test_valid_uuid_returns_id(self):
        """Valid UUID string is returned unchanged."""
        result = _validate_session_id(VALID_SESSION_ID, "test")
        assert result == VALID_SESSION_ID

    def test_none_returns_none(self):
        """None input -> None."""
        result = _validate_session_id(None, "test")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string -> None."""
        result = _validate_session_id("", "test")
        assert result is None

    def test_invalid_uuid_returns_none(self):
        """Non-UUID string -> None."""
        result = _validate_session_id("not-a-valid-uuid", "cookie")
        assert result is None

    def test_partial_uuid_returns_none(self):
        """Partial UUID string -> None."""
        result = _validate_session_id("12345678", "header")
        assert result is None


# --- get_chat_context ---


class TestGetChatContext:
    """Tests for get_chat_context dependency."""

    @patch("backend.session.dependencies.get_client_ip", return_value="192.168.1.100")
    async def test_authenticated_user_no_cookie(
        self, mock_ip, mock_request, mock_user, mock_db, mock_rate_limiter
    ):
        """Authenticated user without session cookie -> user context."""
        result = await get_chat_context(
            request=mock_request,
            user=mock_user,
            token="bearer-token",
            session_id_cookie=None,
            db=mock_db,
            rate_limiter=mock_rate_limiter,
        )

        assert result.is_authenticated is True
        assert result.user_id == FIXED_UUID
        assert result.session_id is None
        assert result.access_token == "bearer-token"
        assert result.anonymous_session_id is None
        assert result.scopes == {"openid", "profile", "api:read"}

    @patch("backend.session.dependencies.get_client_ip", return_value="192.168.1.100")
    async def test_authenticated_user_with_anonymous_cookie(
        self, mock_ip, mock_request, mock_user, mock_db, mock_rate_limiter
    ):
        """Authenticated user with anonymous session cookie -> migration path."""
        result = await get_chat_context(
            request=mock_request,
            user=mock_user,
            token="bearer-token",
            session_id_cookie=VALID_SESSION_ID,
            db=mock_db,
            rate_limiter=mock_rate_limiter,
        )

        assert result.is_authenticated is True
        assert result.user_id == FIXED_UUID
        assert result.session_id is None
        assert result.anonymous_session_id == VALID_SESSION_ID

    @patch("backend.session.dependencies.SessionService")
    @patch("backend.session.dependencies.get_client_ip", return_value="10.0.0.1")
    async def test_anonymous_valid_existing_session(
        self,
        mock_ip,
        mock_session_cls,
        mock_request,
        mock_db,
        mock_rate_limiter,
        mock_session_service,
    ):
        """Anonymous user with valid existing session from cookie."""
        mock_session_service.get = AsyncMock(
            return_value={"session_id": VALID_SESSION_ID, "created_at": "2024-01-01"}
        )
        mock_session_cls.return_value = mock_session_service

        result = await get_chat_context(
            request=mock_request,
            user=None,
            token=None,
            session_id_cookie=VALID_SESSION_ID,
            db=mock_db,
            rate_limiter=mock_rate_limiter,
        )

        assert result.is_authenticated is False
        assert result.session_id == VALID_SESSION_ID
        assert result.user_id is None
        assert result.session_created is False
        mock_session_service.close.assert_awaited_once()

    @patch("backend.session.dependencies.SessionService")
    @patch("backend.session.dependencies.get_client_ip", return_value="10.0.0.1")
    async def test_anonymous_cookie_session_not_found_creates_session(
        self,
        mock_ip,
        mock_session_cls,
        mock_request,
        mock_db,
        mock_rate_limiter,
        mock_session_service,
    ):
        """Cookie session not found in DB, rate limit OK -> create new session."""
        mock_session_service.get = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session_service
        mock_rate_limiter.check_session_creation_limit = AsyncMock(return_value=(True, 4, 3600))

        result = await get_chat_context(
            request=mock_request,
            user=None,
            token=None,
            session_id_cookie=VALID_SESSION_ID,
            db=mock_db,
            rate_limiter=mock_rate_limiter,
        )

        assert result.is_authenticated is False
        assert result.session_id == VALID_SESSION_ID
        assert result.session_created is True
        mock_session_service.create.assert_awaited_once_with(VALID_SESSION_ID)
        mock_rate_limiter.record_session_creation.assert_awaited_once_with("10.0.0.1")
        mock_session_service.close.assert_awaited_once()

    @patch("backend.session.dependencies.SessionService")
    @patch("backend.session.dependencies.get_client_ip", return_value="10.0.0.1")
    async def test_anonymous_cookie_session_not_found_rate_limit_exceeded(
        self,
        mock_ip,
        mock_session_cls,
        mock_request,
        mock_db,
        mock_rate_limiter,
        mock_session_service,
    ):
        """Cookie session not found, rate limit exceeded -> 429."""
        mock_session_service.get = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session_service
        mock_rate_limiter.check_session_creation_limit = AsyncMock(return_value=(False, 0, 7200))

        with pytest.raises(HTTPException) as exc_info:
            await get_chat_context(
                request=mock_request,
                user=None,
                token=None,
                session_id_cookie=VALID_SESSION_ID,
                db=mock_db,
                rate_limiter=mock_rate_limiter,
            )

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        mock_session_service.close.assert_awaited_once()

    @patch("backend.session.dependencies.SessionService")
    @patch("backend.session.dependencies.get_client_ip", return_value="10.0.0.1")
    async def test_no_cookie_no_user_auto_create_success(
        self,
        mock_ip,
        mock_session_cls,
        mock_request,
        mock_db,
        mock_rate_limiter,
        mock_session_service,
    ):
        """No cookie, no user, rate limit OK -> auto-create session."""
        mock_session_cls.return_value = mock_session_service
        mock_rate_limiter.check_session_creation_limit = AsyncMock(return_value=(True, 3, 3600))

        result = await get_chat_context(
            request=mock_request,
            user=None,
            token=None,
            session_id_cookie=None,
            db=mock_db,
            rate_limiter=mock_rate_limiter,
        )

        assert result.is_authenticated is False
        assert result.user_id is None
        assert result.session_id is not None
        # Verify the auto-generated session_id is a valid UUID
        uuid.UUID(result.session_id)
        assert result.session_created is True
        mock_session_service.create.assert_awaited_once()
        mock_rate_limiter.record_session_creation.assert_awaited_once_with("10.0.0.1")
        mock_session_service.close.assert_awaited_once()

    @patch("backend.session.dependencies.get_client_ip", return_value="10.0.0.1")
    async def test_no_cookie_no_user_auto_create_rate_limit_exceeded(
        self,
        mock_ip,
        mock_request,
        mock_db,
        mock_rate_limiter,
    ):
        """No cookie, no user, rate limit exceeded -> 429."""
        mock_rate_limiter.check_session_creation_limit = AsyncMock(return_value=(False, 0, 86400))

        with pytest.raises(HTTPException) as exc_info:
            await get_chat_context(
                request=mock_request,
                user=None,
                token=None,
                session_id_cookie=None,
                db=mock_db,
                rate_limiter=mock_rate_limiter,
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"] == "86400"


# --- ChatContext.owner_id ---


class TestChatContextOwnerId:
    """Tests for ChatContext.owner_id property."""

    def test_owner_id_with_user_id(self):
        """owner_id returns user_id when present."""
        ctx = ChatContext(
            user_id=FIXED_UUID,
            session_id="some-session",
            is_authenticated=True,
        )
        assert ctx.owner_id == str(FIXED_UUID)

    def test_owner_id_with_session_id_only(self):
        """owner_id returns session_id when no user_id."""
        ctx = ChatContext(
            user_id=None,
            session_id=VALID_SESSION_ID,
            is_authenticated=False,
        )
        assert ctx.owner_id == VALID_SESSION_ID

    def test_owner_id_with_neither(self):
        """owner_id returns None when neither user_id nor session_id."""
        ctx = ChatContext(
            user_id=None,
            session_id=None,
            is_authenticated=False,
        )
        assert ctx.owner_id is None


# --- require_session_or_auth ---


class TestRequireSessionOrAuth:
    """Tests for require_session_or_auth dependency."""

    async def test_with_user_id_returns_context(self):
        """Context with user_id -> return context."""
        ctx = ChatContext(
            user_id=FIXED_UUID,
            session_id=None,
            is_authenticated=True,
        )
        result = await require_session_or_auth(context=ctx)
        assert result is ctx

    async def test_with_session_id_returns_context(self):
        """Context with session_id -> return context."""
        ctx = ChatContext(
            user_id=None,
            session_id=VALID_SESSION_ID,
            is_authenticated=False,
        )
        result = await require_session_or_auth(context=ctx)
        assert result is ctx

    async def test_with_neither_raises_401(self):
        """Context with neither user_id nor session_id -> 401."""
        ctx = ChatContext(
            user_id=None,
            session_id=None,
            is_authenticated=False,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_session_or_auth(context=ctx)
        assert exc_info.value.status_code == 401
        assert "Authentication or session cookie required" in exc_info.value.detail
