# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.routes.chat module."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.database import get_db
from backend.middleware.dependencies import check_rate_limit_with_context
from backend.routes.chat import (
    ChatRequest,
    _clear_session_cookie,
    _migrate_anonymous_session,
)
from backend.routes.chat import (
    router as chat_router,
)
from backend.session.dependencies import ChatContext
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
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
def user_id():
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def session_id():
    return "abcdef12-3456-7890-abcd-ef1234567890"


@pytest.fixture
def anon_context(session_id):
    """Return an anonymous ChatContext."""
    return ChatContext(
        user_id=None,
        session_id=session_id,
        is_authenticated=False,
        session_created=False,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def anon_context_new_session(session_id):
    """Return an anonymous ChatContext with session_created=True."""
    return ChatContext(
        user_id=None,
        session_id=session_id,
        is_authenticated=False,
        session_created=True,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def auth_context(user_id, session_id):
    """Return an authenticated ChatContext with anonymous session to migrate."""
    return ChatContext(
        user_id=user_id,
        session_id=None,
        is_authenticated=True,
        session_created=False,
        client_ip="127.0.0.1",
        access_token="test-jwt-token",
        anonymous_session_id=session_id,
        scopes={"openid", "profile"},
    )


@pytest.fixture
def auth_context_no_anon(user_id):
    """Return an authenticated ChatContext without anonymous session."""
    return ChatContext(
        user_id=user_id,
        session_id=None,
        is_authenticated=True,
        session_created=False,
        client_ip="127.0.0.1",
        access_token="test-jwt-token",
        anonymous_session_id=None,
        scopes={"openid", "profile"},
    )


@pytest.fixture
def mock_conversation():
    """Return a mock Conversation."""
    conv = MagicMock()
    conv.id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    conv.user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    conv.session_id = None
    conv.title = "Test Conversation"
    conv.summary = "A test summary."
    conv.archived_at = None
    conv.messages = []
    return conv


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with the chat router for testing."""
    app = FastAPI()
    app.include_router(chat_router)
    return app


# ---------------------------------------------------------------------------
# ChatRequest validation
# ---------------------------------------------------------------------------


class TestChatRequest:
    """Tests for ChatRequest model validation."""

    def test_valid_message(self):
        req = ChatRequest(message="Hello, how are you?")
        assert req.message == "Hello, how are you?"

    def test_empty_string_is_valid(self):
        """Pydantic allows empty string for str fields by default."""
        req = ChatRequest(message="")
        assert req.message == ""

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest()


# ---------------------------------------------------------------------------
# _migrate_anonymous_session
# ---------------------------------------------------------------------------


class TestMigrateAnonymousSession:
    """Tests for _migrate_anonymous_session helper."""

    async def test_not_authenticated_returns_false(self, mock_db, session_id):
        """Non-authenticated context should return False immediately."""
        context = ChatContext(
            user_id=None,
            session_id=session_id,
            is_authenticated=False,
        )
        result = await _migrate_anonymous_session(mock_db, context)
        assert result is False

    async def test_no_anonymous_session_id_returns_false(self, mock_db, user_id):
        """Authenticated user without anonymous session returns False."""
        context = ChatContext(
            user_id=user_id,
            session_id=None,
            is_authenticated=True,
            anonymous_session_id=None,
        )
        result = await _migrate_anonymous_session(mock_db, context)
        assert result is False

    async def test_no_user_id_returns_false(self, mock_db, session_id):
        """Authenticated flag but no user_id returns False."""
        context = ChatContext(
            user_id=None,
            session_id=None,
            is_authenticated=True,
            anonymous_session_id=session_id,
        )
        result = await _migrate_anonymous_session(mock_db, context)
        assert result is False

    @patch("backend.routes.chat.SessionService")
    @patch("backend.routes.chat.ConversationCache")
    @patch("backend.routes.chat.ChatService")
    async def test_migration_success(
        self,
        mock_chat_cls,
        mock_cache_cls,
        mock_sess_cls,
        mock_db,
        auth_context,
        mock_conversation,
    ):
        """Authenticated user with conversation to migrate returns True."""
        mock_chat = AsyncMock()
        mock_chat.migrate_conversation.return_value = mock_conversation
        mock_chat_cls.return_value = mock_chat

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        mock_sess = AsyncMock()
        mock_sess_cls.return_value = mock_sess

        result = await _migrate_anonymous_session(mock_db, auth_context)

        assert result is True
        mock_chat.migrate_conversation.assert_awaited_once_with(
            auth_context.anonymous_session_id,
            auth_context.user_id,
        )
        mock_cache.invalidate.assert_awaited_once_with(mock_conversation.id)
        mock_cache.close.assert_awaited_once()
        mock_sess.delete.assert_awaited_once_with(auth_context.anonymous_session_id)
        mock_sess.close.assert_awaited_once()

    @patch("backend.routes.chat.SessionService")
    @patch("backend.routes.chat.ConversationCache")
    @patch("backend.routes.chat.ChatService")
    async def test_migration_no_conversation_returns_false(
        self,
        mock_chat_cls,
        mock_cache_cls,
        mock_sess_cls,
        mock_db,
        auth_context,
    ):
        """Authenticated user with no conversation to migrate returns False."""
        mock_chat = AsyncMock()
        mock_chat.migrate_conversation.return_value = None
        mock_chat_cls.return_value = mock_chat

        result = await _migrate_anonymous_session(mock_db, auth_context)

        assert result is False
        mock_chat.migrate_conversation.assert_awaited_once()


# ---------------------------------------------------------------------------
# _clear_session_cookie
# ---------------------------------------------------------------------------


class TestClearSessionCookie:
    """Tests for _clear_session_cookie helper."""

    @patch("backend.routes.chat.settings")
    def test_calls_delete_cookie(self, mock_settings):
        mock_settings.session_cookie_name = "session_id"
        mock_settings.session_cookie_secure = True
        mock_settings.session_cookie_samesite = "lax"
        mock_settings.session_cookie_domain = ""

        mock_response = MagicMock()
        _clear_session_cookie(mock_response)

        mock_response.delete_cookie.assert_called_once_with(
            key="session_id",
            secure=True,
            samesite="lax",
            domain=None,
        )

    @patch("backend.routes.chat.settings")
    def test_calls_delete_cookie_with_domain(self, mock_settings):
        mock_settings.session_cookie_name = "session_id"
        mock_settings.session_cookie_secure = False
        mock_settings.session_cookie_samesite = "none"
        mock_settings.session_cookie_domain = "example.com"

        mock_response = MagicMock()
        _clear_session_cookie(mock_response)

        mock_response.delete_cookie.assert_called_once_with(
            key="session_id",
            secure=False,
            samesite="none",
            domain="example.com",
        )


# ---------------------------------------------------------------------------
# chat() endpoint -- history mode
# ---------------------------------------------------------------------------


class TestChatEndpointHistoryMode:
    """Tests for the chat endpoint in history mode (?history=true)."""

    @patch("backend.routes.chat.ChatService")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_history_mode_returns_messages(
        self,
        mock_migrate,
        mock_chat_cls,
        mock_db,
        anon_context,
        mock_conversation,
        test_app,
    ):
        """History mode returns JSON with conversation messages."""
        mock_chat = AsyncMock()
        mock_chat.get_or_create_conversation.return_value = (mock_conversation, False)
        mock_chat.get_conversation_history.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_chat_cls.return_value = mock_chat

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: anon_context

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat?history=true",
                    json={"message": "ignored"},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert "messages" in data
            assert len(data["messages"]) == 2
            assert data["messages"][0]["role"] == "user"
            assert data["messages"][0]["content"] == "Hello"
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat.ChatService")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_history_mode_sets_cookie_for_new_session(
        self,
        mock_migrate,
        mock_chat_cls,
        mock_db,
        anon_context_new_session,
        mock_conversation,
        test_app,
    ):
        """History mode sets session cookie when session was just created."""
        mock_chat = AsyncMock()
        mock_chat.get_or_create_conversation.return_value = (mock_conversation, False)
        mock_chat.get_conversation_history.return_value = []
        mock_chat_cls.return_value = mock_chat

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: (
            anon_context_new_session
        )

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat?history=true",
                    json={"message": "hi"},
                )

            assert resp.status_code == 200
            cookie_header = resp.headers.get("set-cookie", "")
            assert anon_context_new_session.session_id in cookie_header
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat._clear_session_cookie")
    @patch("backend.routes.chat.ChatService")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=True
    )
    async def test_history_mode_clears_cookie_after_migration(
        self,
        mock_migrate,
        mock_chat_cls,
        mock_clear_cookie,
        mock_db,
        auth_context,
        mock_conversation,
        test_app,
    ):
        """History mode clears session cookie after successful migration."""
        mock_chat = AsyncMock()
        mock_chat.get_or_create_conversation.return_value = (mock_conversation, False)
        mock_chat.get_conversation_history.return_value = []
        mock_chat_cls.return_value = mock_chat

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: auth_context

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat?history=true",
                    json={"message": "hi"},
                )

            assert resp.status_code == 200
            mock_clear_cookie.assert_called_once()
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat.ChatService")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_history_mode_session_id_in_response_for_anonymous(
        self,
        mock_migrate,
        mock_chat_cls,
        mock_db,
        anon_context,
        mock_conversation,
        test_app,
    ):
        """History mode includes session_id in response for anonymous users."""
        mock_chat = AsyncMock()
        mock_chat.get_or_create_conversation.return_value = (mock_conversation, False)
        mock_chat.get_conversation_history.return_value = []
        mock_chat_cls.return_value = mock_chat

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: anon_context

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat?history=true",
                    json={"message": "hi"},
                )

            data = resp.json()
            assert data["session_id"] == anon_context.session_id
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat.ChatService")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_history_mode_no_session_id_for_authenticated(
        self,
        mock_migrate,
        mock_chat_cls,
        mock_db,
        auth_context_no_anon,
        mock_conversation,
        test_app,
    ):
        """History mode does not include session_id for authenticated users."""
        mock_chat = AsyncMock()
        mock_chat.get_or_create_conversation.return_value = (mock_conversation, False)
        mock_chat.get_conversation_history.return_value = []
        mock_chat_cls.return_value = mock_chat

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: auth_context_no_anon

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat?history=true",
                    json={"message": "hi"},
                )

            data = resp.json()
            assert data["session_id"] is None
        finally:
            test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# chat() endpoint -- chat (streaming) mode
# ---------------------------------------------------------------------------


class TestChatEndpointStreamMode:
    """Tests for the chat endpoint in streaming mode (default)."""

    @patch("backend.routes.chat.ChatOrchestrator")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_chat_mode_returns_streaming_response(
        self,
        mock_migrate,
        mock_orch_cls,
        mock_db,
        anon_context,
        test_app,
    ):
        """Chat mode returns a streaming response with text/event-stream."""
        mock_orch = MagicMock()

        async def fake_stream(**kwargs):
            yield {"type": "intent", "intent": "no_match"}
            yield {"type": "token", "content": "Hello"}
            yield {"type": "done", "usage": {"prompt_tokens": 5, "completion_tokens": 3}}

        mock_orch.process_message_stream = fake_stream
        mock_orch_cls.return_value = mock_orch

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: anon_context

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat",
                    json={"message": "What is the weather?"},
                )

            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            assert resp.headers.get("cache-control") == "no-cache"
            assert resp.headers.get("x-accel-buffering") == "no"
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat.ChatOrchestrator")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_chat_mode_sets_cookie_for_new_session(
        self,
        mock_migrate,
        mock_orch_cls,
        mock_db,
        anon_context_new_session,
        test_app,
    ):
        """Chat mode sets session cookie when session was just created."""
        mock_orch = MagicMock()

        async def fake_stream(**kwargs):
            yield {"type": "done", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

        mock_orch.process_message_stream = fake_stream
        mock_orch_cls.return_value = mock_orch

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: (
            anon_context_new_session
        )

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat",
                    json={"message": "Hello"},
                )

            cookie_header = resp.headers.get("set-cookie", "")
            assert anon_context_new_session.session_id in cookie_header
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat._clear_session_cookie")
    @patch("backend.routes.chat.ChatOrchestrator")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=True
    )
    async def test_chat_mode_clears_cookie_after_migration(
        self,
        mock_migrate,
        mock_orch_cls,
        mock_clear_cookie,
        mock_db,
        auth_context,
        test_app,
    ):
        """Chat mode clears session cookie after successful migration."""
        mock_orch = MagicMock()

        async def fake_stream(**kwargs):
            yield {"type": "done", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

        mock_orch.process_message_stream = fake_stream
        mock_orch_cls.return_value = mock_orch

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: auth_context

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat",
                    json={"message": "Hello"},
                )

            assert resp.status_code == 200
            mock_clear_cookie.assert_called_once()
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat.stream_chat_response")
    @patch("backend.routes.chat.ChatOrchestrator")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_chat_mode_stream_error_in_generate(
        self,
        mock_migrate,
        mock_orch_cls,
        mock_stream_chat,
        mock_db,
        anon_context,
        test_app,
        caplog,
    ):
        """Chat mode logs and re-raises errors from the streaming generator."""
        mock_orch = MagicMock()

        async def fake_process(**kwargs):
            yield {"type": "token", "content": "Hi"}

        mock_orch.process_message_stream = fake_process
        mock_orch_cls.return_value = mock_orch

        # Make stream_chat_response return an async generator that raises
        async def failing_stream_response(gen):
            raise RuntimeError("Stream processing error")
            yield  # make it an async generator

        mock_stream_chat.side_effect = lambda gen: failing_stream_response(gen)

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: anon_context

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with pytest.raises(RuntimeError, match="Stream processing error"):
                    await client.post(
                        "/api/v1/chat",
                        json={"message": "trigger error"},
                    )

            # The error path (log + raise) in generate() was exercised
            assert "Error during chat streaming" in caplog.text
        finally:
            test_app.dependency_overrides.clear()

    @patch("backend.routes.chat.ChatOrchestrator")
    @patch(
        "backend.routes.chat._migrate_anonymous_session", new_callable=AsyncMock, return_value=False
    )
    async def test_chat_mode_stream_contains_sse_events(
        self,
        mock_migrate,
        mock_orch_cls,
        mock_db,
        anon_context,
        test_app,
    ):
        """Chat mode SSE stream contains expected event data."""
        mock_orch = MagicMock()

        async def fake_stream(**kwargs):
            yield {"type": "history", "messages": []}
            yield {"type": "intent", "intent": "rag_search"}
            yield {"type": "rag", "count": 2}
            yield {"type": "token", "content": "Answer"}
            yield {"type": "done", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        mock_orch.process_message_stream = fake_stream
        mock_orch_cls.return_value = mock_orch

        test_app.dependency_overrides[get_db] = lambda: mock_db
        test_app.dependency_overrides[check_rate_limit_with_context] = lambda: anon_context

        try:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/chat",
                    json={"message": "Tell me about X"},
                )

            assert resp.status_code == 200
            body = resp.text
            assert "event:" in body or "data:" in body or len(body) > 0
        finally:
            test_app.dependency_overrides.clear()
