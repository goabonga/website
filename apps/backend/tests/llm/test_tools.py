# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.llm.tools — ToolRegistry and built-in tool handlers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.llm.tools import (
    Tool,
    ToolContext,
    ToolRegistry,
    ToolResult,
    auth_action,
    get_session_info,
    help_me,
    new_conversation,
    search_knowledge,
    tool_registry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry():
    """Return a fresh ToolRegistry (isolated from the global one)."""
    return ToolRegistry()


@pytest.fixture
def sample_handler():
    """Return an async handler that returns a successful ToolResult."""
    handler = AsyncMock(return_value=ToolResult(success=True, data={"ok": True}))
    return handler


@pytest.fixture
def context_handler():
    """Return an async handler that expects a ToolContext as first arg."""
    handler = AsyncMock(return_value=ToolResult(success=True, data={"ctx": True}))
    return handler


@pytest.fixture
def user_id():
    """Return a fixed user UUID."""
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def conversation_id():
    """Return a fixed conversation UUID."""
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def session_id():
    """Return a fixed session ID."""
    return "abcdef12-3456-7890-abcd-ef1234567890"


# ===========================================================================
# Tests for ToolRegistry core methods
# ===========================================================================


class TestToolRegistryRegister:
    """Tests for ToolRegistry.register()."""

    def test_register_adds_tool_to_registry(self, registry, sample_handler):
        """register() adds a tool that can be retrieved by name."""

        @registry.register(
            name="my_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
        )
        async def my_tool():
            return ToolResult(success=True, data="test")

        assert "my_tool" in registry._tools
        assert registry._tools["my_tool"].name == "my_tool"
        assert registry._tools["my_tool"].description == "A test tool"


class TestToolRegistryGetTool:
    """Tests for ToolRegistry.get_tool()."""

    def test_get_tool_returns_registered_tool(self, registry):
        """get_tool() returns the Tool object for a registered name."""

        @registry.register(
            name="test_tool",
            description="desc",
            parameters={"type": "object", "properties": {}},
        )
        async def test_tool():
            return ToolResult(success=True, data="ok")

        tool = registry.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"

    def test_get_tool_returns_none_for_unknown(self, registry):
        """get_tool() returns None when the tool does not exist."""
        assert registry.get_tool("nonexistent_tool") is None


class TestToolRegistryIsToolAccessible:
    """Tests for ToolRegistry._is_tool_accessible()."""

    def test_public_tool_always_accessible(self, registry):
        """A tool with required_scopes=None is always accessible."""
        tool = Tool(
            name="public_tool",
            description="public",
            parameters={},
            handler=AsyncMock(),
            required_scopes=None,
        )
        assert registry._is_tool_accessible(tool, user_scopes=None) is True
        assert registry._is_tool_accessible(tool, user_scopes=set()) is True
        assert registry._is_tool_accessible(tool, user_scopes={"admin"}) is True

    def test_scoped_tool_with_matching_scopes(self, registry):
        """A scoped tool is accessible when user has all required scopes."""
        tool = Tool(
            name="scoped_tool",
            description="scoped",
            parameters={},
            handler=AsyncMock(),
            required_scopes={"api:read", "api:write"},
        )
        user_scopes = {"api:read", "api:write", "admin"}
        assert registry._is_tool_accessible(tool, user_scopes) is True

    def test_scoped_tool_without_matching_scopes(self, registry):
        """A scoped tool is NOT accessible when user lacks required scopes."""
        tool = Tool(
            name="scoped_tool",
            description="scoped",
            parameters={},
            handler=AsyncMock(),
            required_scopes={"api:read", "api:write"},
        )
        user_scopes = {"api:read"}  # Missing api:write
        assert registry._is_tool_accessible(tool, user_scopes) is False

    def test_scoped_tool_with_none_user_scopes(self, registry):
        """A scoped tool is NOT accessible when user_scopes is None (anonymous)."""
        tool = Tool(
            name="scoped_tool",
            description="scoped",
            parameters={},
            handler=AsyncMock(),
            required_scopes={"api:read"},
        )
        assert registry._is_tool_accessible(tool, user_scopes=None) is False


class TestToolRegistryGetOpenaiTools:
    """Tests for ToolRegistry.get_openai_tools()."""

    def test_get_openai_tools_returns_openai_format(self, registry):
        """get_openai_tools() returns tools in the expected OpenAI format."""

        @registry.register(
            name="my_func",
            description="Do something",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        async def my_func(x: str):
            return ToolResult(success=True, data=x)

        tools = registry.get_openai_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "my_func"
        assert tools[0]["function"]["description"] == "Do something"
        assert tools[0]["function"]["parameters"]["properties"]["x"]["type"] == "string"

    def test_get_openai_tools_filters_by_user_scopes(self, registry):
        """get_openai_tools() only returns tools accessible to the given user_scopes."""

        @registry.register(
            name="public_tool",
            description="Public tool",
            parameters={"type": "object", "properties": {}},
        )
        async def public_tool():
            return ToolResult(success=True, data="public")

        @registry.register(
            name="admin_tool",
            description="Admin only",
            parameters={"type": "object", "properties": {}},
            required_scopes={"admin"},
        )
        async def admin_tool():
            return ToolResult(success=True, data="admin")

        # No scopes: only public tools
        tools_anon = registry.get_openai_tools(user_scopes=None)
        assert len(tools_anon) == 1
        assert tools_anon[0]["function"]["name"] == "public_tool"

        # With admin scope: both tools
        tools_admin = registry.get_openai_tools(user_scopes={"admin"})
        assert len(tools_admin) == 2
        names = {t["function"]["name"] for t in tools_admin}
        assert names == {"public_tool", "admin_tool"}


class TestToolRegistryExecute:
    """Tests for ToolRegistry.execute()."""

    async def test_execute_calls_handler_without_context(self, registry):
        """execute() calls the handler with arguments when requires_context=False."""
        handler = AsyncMock(return_value=ToolResult(success=True, data="result"))

        @registry.register(
            name="simple_tool",
            description="Simple",
            parameters={"type": "object", "properties": {}},
        )
        async def simple_tool(query: str):
            return await handler(query=query)

        result = await registry.execute("simple_tool", {"query": "test"})

        assert result.success is True
        handler.assert_awaited_once_with(query="test")

    async def test_execute_calls_handler_with_context(self, registry):
        """execute() passes ToolContext as first arg when requires_context=True."""
        received_context = {}

        @registry.register(
            name="ctx_tool",
            description="Context tool",
            parameters={"type": "object", "properties": {}},
            requires_context=True,
        )
        async def ctx_tool(context: ToolContext, **kwargs):
            received_context["ctx"] = context
            return ToolResult(success=True, data="ok")

        ctx = ToolContext(
            user_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            is_authenticated=True,
        )

        result = await registry.execute("ctx_tool", {}, context=ctx)

        assert result.success is True
        assert received_context["ctx"].user_id == uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert received_context["ctx"].is_authenticated is True

    async def test_execute_unknown_tool_returns_error(self, registry):
        """execute() returns an error ToolResult for an unknown tool name."""
        result = await registry.execute("nonexistent_tool", {})

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error

    async def test_execute_access_denied_returns_error(self, registry):
        """execute() returns an error ToolResult when user lacks required scopes."""

        @registry.register(
            name="admin_only",
            description="Admin only",
            parameters={"type": "object", "properties": {}},
            required_scopes={"admin"},
        )
        async def admin_only():
            return ToolResult(success=True, data="secret")

        # Execute without scopes
        ctx = ToolContext(scopes=None)
        result = await registry.execute("admin_only", {}, context=ctx)

        assert result.success is False
        assert "Access denied" in result.error

    async def test_execute_handler_exception_returns_error(self, registry):
        """execute() catches handler exceptions and returns an error ToolResult."""

        @registry.register(
            name="broken_tool",
            description="Broken",
            parameters={"type": "object", "properties": {}},
        )
        async def broken_tool():
            raise ValueError("Something went wrong")

        result = await registry.execute("broken_tool", {})

        assert result.success is False
        assert "Something went wrong" in result.error

    async def test_execute_handler_returns_failed_result(self, registry):
        """execute() logs and returns ToolResult when handler returns success=False."""

        @registry.register(
            name="failing_tool",
            description="Fails gracefully",
            parameters={"type": "object", "properties": {}},
        )
        async def failing_tool():
            return ToolResult(success=False, data=None, error="Something went wrong gracefully")

        result = await registry.execute("failing_tool", {})

        assert result.success is False
        assert result.error == "Something went wrong gracefully"


# ===========================================================================
# Tests for built-in tools
# ===========================================================================


class TestSearchKnowledgeTool:
    """Tests for the search_knowledge built-in tool."""

    async def test_search_knowledge_no_results(self):
        """search_knowledge() returns no-results message when KB returns empty."""
        mock_kb_instance = AsyncMock()
        mock_kb_instance.search = AsyncMock(return_value=[])

        with (
            patch("backend.rag.knowledge_base.KnowledgeBase", return_value=mock_kb_instance),
            patch("backend.llm.tools.async_session_maker") as mock_session_maker,
        ):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            context = ToolContext(scopes={"openid"})
            result = await search_knowledge(context=context, query="Python async")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data["query"] == "Python async"
        assert result.data["namespace"] is None
        assert "No relevant information found" in result.data["message"]
        mock_kb_instance.search.assert_awaited_once_with(
            "Python async", namespace_slug=None, user_scopes={"openid"}
        )

    async def test_search_knowledge_with_results(self):
        """search_knowledge() returns formatted results from KnowledgeBase."""
        mock_kb_instance = AsyncMock()
        mock_kb_instance.search = AsyncMock(
            return_value=[
                {
                    "question": "What is Python?",
                    "answer": "A programming language.",
                    "similarity": 0.92,
                },
            ]
        )

        with (
            patch("backend.rag.knowledge_base.KnowledgeBase", return_value=mock_kb_instance),
            patch("backend.llm.tools.async_session_maker") as mock_session_maker,
        ):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            context = ToolContext(scopes={"openid"})
            result = await search_knowledge(context=context, query="Python")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data["query"] == "Python"
        assert result.data["namespace"] is None
        assert len(result.data["results"]) == 1
        assert result.data["results"][0]["answer"] == "A programming language."
        assert result.data["results"][0]["similarity"] == 0.92

    async def test_search_knowledge_with_namespace(self):
        """search_knowledge() passes namespace_slug to KnowledgeBase.search()."""
        mock_kb_instance = AsyncMock()
        mock_kb_instance.search = AsyncMock(
            return_value=[
                {"question": "Q?", "answer": "A.", "similarity": 0.9},
            ]
        )

        with (
            patch("backend.rag.knowledge_base.KnowledgeBase", return_value=mock_kb_instance),
            patch("backend.llm.tools.async_session_maker") as mock_session_maker,
        ):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            context = ToolContext(scopes={"openid"})
            result = await search_knowledge(context=context, query="pricing", namespace="faq")

        assert result.success is True
        assert result.data["namespace"] == "faq"
        assert len(result.data["results"]) == 1
        mock_kb_instance.search.assert_awaited_once_with(
            "pricing", namespace_slug="faq", user_scopes={"openid"}
        )

    async def test_search_knowledge_with_namespace_no_results(self):
        """search_knowledge() includes namespace in no-results response."""
        mock_kb_instance = AsyncMock()
        mock_kb_instance.search = AsyncMock(return_value=[])

        with (
            patch("backend.rag.knowledge_base.KnowledgeBase", return_value=mock_kb_instance),
            patch("backend.llm.tools.async_session_maker") as mock_session_maker,
        ):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            context = ToolContext(scopes={"openid"})
            result = await search_knowledge(context=context, query="test", namespace="docs")

        assert result.success is True
        assert result.data["namespace"] == "docs"
        assert "No relevant information found" in result.data["message"]


class TestHelpMeTool:
    """Tests for the help_me built-in tool."""

    async def test_help_me_lists_non_hidden_tools(self):
        """help_me() lists all tools except those marked as hidden."""
        result = await help_me()

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "tools" in result.data
        assert "message" in result.data

        tool_names = [t["name"] for t in result.data["tools"]]
        # help_me itself is hidden=True, so it should not appear
        assert "help_me" not in tool_names
        # search_knowledge is not hidden, so it should appear
        assert "search_knowledge" in tool_names


class TestGetSessionInfoTool:
    """Tests for the get_session_info built-in tool."""

    async def test_anonymous_user(self, session_id, conversation_id):
        """get_session_info() returns anonymous info when not authenticated."""
        ctx = ToolContext(
            is_authenticated=False,
            session_id=session_id,
            conversation_id=conversation_id,
        )

        result = await get_session_info(ctx)

        assert result.success is True
        assert result.data["authenticated"] is False
        assert result.data["session_id"] == session_id
        assert "not authenticated" in result.data["message"]

    @patch("backend.llm.tools.settings")
    @patch("backend.llm.tools._fetch_userinfo")
    async def test_authenticated_user_with_userinfo(
        self, mock_fetch, mock_settings, user_id, conversation_id
    ):
        """get_session_info() fetches and returns user profile when authenticated."""
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_fetch.return_value = {
            "name": "John Doe",
            "email": "john@example.com",
            "email_verified": True,
            "preferred_username": "johndoe",
            "picture": "/avatar/johndoe.jpg",
            "locale": "en",
        }

        ctx = ToolContext(
            user_id=user_id,
            is_authenticated=True,
            access_token="fake-jwt-token",
            conversation_id=conversation_id,
        )

        result = await get_session_info(ctx)

        assert result.success is True
        assert result.data["authenticated"] is True
        assert result.data["email"] == "john@example.com"
        assert result.data["name"] == "John Doe"
        assert result.data["email_verified"] is True
        assert "John Doe" in result.data["message"]
        assert result.data["client_action"] == "display_image"
        assert result.data["image_url"] == "https://auth.example.com/avatar/johndoe.jpg"
        assert result.data["image_alt"] == "Profile picture of John Doe"
        mock_fetch.assert_awaited_once_with("fake-jwt-token")

    @patch("backend.llm.tools._fetch_userinfo")
    async def test_authenticated_user_picture_absolute_url(
        self, mock_fetch, user_id, conversation_id
    ):
        """get_session_info() keeps absolute picture URL as-is without prepending issuer."""
        mock_fetch.return_value = {
            "name": "John Doe",
            "picture": "https://auth.goabonga.com/uploads/avatars/abc123.png",
        }

        ctx = ToolContext(
            user_id=user_id,
            is_authenticated=True,
            access_token="fake-jwt-token",
            conversation_id=conversation_id,
        )

        result = await get_session_info(ctx)

        assert result.data["client_action"] == "display_image"
        assert result.data["image_url"] == "https://auth.goabonga.com/uploads/avatars/abc123.png"

    @patch("backend.llm.tools._fetch_userinfo")
    async def test_authenticated_user_userinfo_fails(self, mock_fetch, user_id, conversation_id):
        """get_session_info() falls back gracefully when userinfo fetch fails."""
        mock_fetch.return_value = None

        ctx = ToolContext(
            user_id=user_id,
            is_authenticated=True,
            access_token="bad-token",
            conversation_id=conversation_id,
        )

        result = await get_session_info(ctx)

        assert result.success is True
        assert result.data["authenticated"] is True
        assert str(user_id) in result.data["message"]

    @patch("backend.llm.tools._fetch_userinfo")
    async def test_authenticated_user_no_email(self, mock_fetch, user_id, conversation_id):
        """get_session_info() handles userinfo with no email field."""
        mock_fetch.return_value = {
            "name": "Jane Doe",
            "preferred_username": "janedoe",
        }

        ctx = ToolContext(
            user_id=user_id,
            is_authenticated=True,
            access_token="fake-jwt-token",
            conversation_id=conversation_id,
        )

        result = await get_session_info(ctx)

        assert result.success is True
        assert result.data["authenticated"] is True
        assert result.data["email"] is None
        assert "Jane Doe" in result.data["message"]
        # The message should NOT contain "Email:" since email is None
        assert "Email:" not in result.data["message"]
        # No picture means no client_action
        assert "client_action" not in result.data


class TestAuthActionTool:
    """Tests for the auth_action built-in tool."""

    @patch("backend.llm.tools.settings")
    async def test_login_action(self, mock_settings):
        """auth_action(action='login') returns auth_login client action."""
        mock_settings.oauth2_issuer = "https://auth.example.com"

        ctx = ToolContext(is_authenticated=False)
        result = await auth_action(ctx, action="login")

        assert result.success is True
        assert result.data["client_action"] == "auth_login"
        assert "login" in result.data["message"].lower()

    @patch("backend.llm.tools.settings")
    async def test_logout_when_not_authenticated(self, mock_settings):
        """auth_action(action='logout') warns when user is not logged in."""
        mock_settings.oauth2_issuer = "https://auth.example.com"

        ctx = ToolContext(is_authenticated=False)
        result = await auth_action(ctx, action="logout")

        assert result.success is True
        assert result.data["client_action"] == "none"
        assert "not currently logged in" in result.data["message"]

    @patch("backend.llm.tools.settings")
    async def test_login_when_already_authenticated(self, mock_settings):
        """auth_action(action='login') warns when user is already logged in."""
        mock_settings.oauth2_issuer = "https://auth.example.com"

        ctx = ToolContext(is_authenticated=True)
        result = await auth_action(ctx, action="login")

        assert result.success is True
        assert result.data["client_action"] == "none"
        assert "already logged in" in result.data["message"]

    @patch("backend.llm.tools.settings")
    async def test_auth_not_configured(self, mock_settings):
        """auth_action() returns error when oauth2_issuer is not set."""
        mock_settings.oauth2_issuer = ""

        ctx = ToolContext(is_authenticated=False)
        result = await auth_action(ctx, action="login")

        assert result.success is False
        assert "not configured" in result.error

    @patch("backend.llm.tools.settings")
    async def test_logout_when_authenticated(self, mock_settings):
        """auth_action(action='logout') returns auth_logout for authenticated user."""
        mock_settings.oauth2_issuer = "https://auth.example.com"

        ctx = ToolContext(is_authenticated=True)
        result = await auth_action(ctx, action="logout")

        assert result.success is True
        assert result.data["client_action"] == "auth_logout"

    @patch("backend.llm.tools.settings")
    async def test_unknown_action(self, mock_settings):
        """auth_action() returns error for an unknown action."""
        mock_settings.oauth2_issuer = "https://auth.example.com"

        ctx = ToolContext(is_authenticated=False)
        result = await auth_action(ctx, action="invalid_action")

        assert result.success is False
        assert "Unknown action" in result.error


class TestNewConversationTool:
    """Tests for the new_conversation built-in tool."""

    @patch("backend.llm.tools.async_session_maker")
    async def test_new_conversation_archives_and_returns(
        self, mock_session_maker, user_id, session_id
    ):
        """new_conversation() archives the current conversation and returns success."""
        # Set up the mock async context manager for the session
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock the ChatService
        mock_archived_conv = MagicMock()
        mock_archived_conv.id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        with patch("backend.chat.service.ChatService") as MockChatService:
            mock_service = MockChatService.return_value
            mock_service.archive_conversation = AsyncMock(return_value=mock_archived_conv)

            ctx = ToolContext(
                user_id=user_id,
                session_id=session_id,
            )

            result = await new_conversation(ctx)

        assert result.success is True
        assert result.data["client_action"] == "new_conversation"
        assert result.data["archived_conversation_id"] == str(mock_archived_conv.id)
        assert "archived" in result.data["message"].lower()

    @patch("backend.llm.tools.async_session_maker")
    async def test_new_conversation_no_active_conversation(
        self, mock_session_maker, user_id, session_id
    ):
        """new_conversation() handles the case when no active conversation exists."""
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.chat.service.ChatService") as MockChatService:
            mock_service = MockChatService.return_value
            mock_service.archive_conversation = AsyncMock(return_value=None)

            ctx = ToolContext(
                user_id=user_id,
                session_id=session_id,
            )

            result = await new_conversation(ctx)

        assert result.success is True
        assert result.data["client_action"] == "new_conversation"
        assert "Starting a new conversation" in result.data["message"]

    async def test_new_conversation_without_user_or_session(self):
        """new_conversation() returns error when no user_id or session_id is present."""
        ctx = ToolContext(
            user_id=None,
            session_id=None,
        )

        result = await new_conversation(ctx)

        assert result.success is False
        assert "Cannot start" in result.error


# ===========================================================================
# Tests for _fetch_userinfo
# ===========================================================================


class TestFetchUserinfo:
    """Tests for the _fetch_userinfo helper function."""

    @patch("backend.llm.tools.settings")
    async def test_fetch_userinfo_success(self, mock_settings):
        """_fetch_userinfo() returns user info dict on successful response."""
        from backend.llm.tools import _fetch_userinfo

        mock_settings.oauth2_issuer = "https://auth.example.com"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "John Doe",
            "email": "john@example.com",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.llm.tools.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_userinfo("fake-token")

        assert result == {"name": "John Doe", "email": "john@example.com"}
        mock_client.get.assert_awaited_once_with(
            "https://auth.example.com/userinfo",
            headers={"Authorization": "Bearer fake-token"},
        )

    @patch("backend.llm.tools.settings")
    async def test_fetch_userinfo_no_issuer(self, mock_settings):
        """_fetch_userinfo() returns None when oauth2_issuer is not set."""
        from backend.llm.tools import _fetch_userinfo

        mock_settings.oauth2_issuer = ""

        result = await _fetch_userinfo("fake-token")

        assert result is None

    @patch("backend.llm.tools.settings")
    async def test_fetch_userinfo_error(self, mock_settings):
        """_fetch_userinfo() returns None on httpx.RequestError."""
        import httpx as real_httpx
        from backend.llm.tools import _fetch_userinfo

        mock_settings.oauth2_issuer = "https://auth.example.com"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=real_httpx.RequestError("Connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.llm.tools.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_userinfo("fake-token")

        assert result is None

    @patch("backend.llm.tools.settings")
    async def test_fetch_userinfo_non_200(self, mock_settings):
        """_fetch_userinfo() returns None when response status is not 200."""
        from backend.llm.tools import _fetch_userinfo

        mock_settings.oauth2_issuer = "https://auth.example.com"

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.llm.tools.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_userinfo("fake-token")

        assert result is None


# ===========================================================================
# Tests for get_session_info - authenticated but no token
# ===========================================================================


class TestGetSessionInfoNoToken:
    """Tests for get_session_info when authenticated but no access_token."""

    async def test_get_session_info_authenticated_no_token(self, user_id, conversation_id):
        """get_session_info() returns basic info when authenticated but access_token is None."""
        ctx = ToolContext(
            user_id=user_id,
            is_authenticated=True,
            access_token=None,
            conversation_id=conversation_id,
        )

        result = await get_session_info(ctx)

        assert result.success is True
        assert result.data["authenticated"] is True
        assert result.data["user_id"] == str(user_id)
        assert result.data["conversation_id"] == str(conversation_id)
        assert str(user_id) in result.data["message"]


# ===========================================================================
# Tests for auth_action - additional branches
# ===========================================================================


class TestAuthActionAdditional:
    """Additional tests for auth_action to cover remaining branches."""

    @patch("backend.llm.tools.settings")
    async def test_auth_action_unknown_action(self, mock_settings):
        """auth_action() returns error for an unknown action value."""
        mock_settings.oauth2_issuer = "https://auth.example.com"

        ctx = ToolContext(is_authenticated=False)
        result = await auth_action(ctx, action="delete_account")

        assert result.success is False
        assert "Unknown action" in result.error

    @patch("backend.llm.tools.settings")
    async def test_auth_action_no_oauth2(self, mock_settings):
        """auth_action() returns error when oauth2_issuer is not configured."""
        mock_settings.oauth2_issuer = ""

        ctx = ToolContext(is_authenticated=False)
        result = await auth_action(ctx, action="login")

        assert result.success is False
        assert "not configured" in result.error


# ===========================================================================
# Tests for help_me - tool listing with examples
# ===========================================================================


class TestHelpMeToolListing:
    """Tests for help_me tool listing and examples output."""

    async def test_help_me_lists_tools_with_examples(self):
        """help_me() lists tools with their examples in the message."""
        result = await help_me()

        assert result.success is True
        # The message should contain example prompts from TOOL_EXAMPLES
        assert "Examples:" in result.data["message"]
        # Check that at least one tool has examples in the output
        has_tool_with_examples = any(len(t["examples"]) > 0 for t in result.data["tools"])
        assert has_tool_with_examples

    async def test_help_me_tool_without_examples(self):
        """help_me() handles tools that have no examples in TOOL_EXAMPLES."""

        # Register a temporary non-hidden tool with no examples
        @tool_registry.register(
            name="_test_no_examples_tool",
            description="Tool with no examples for testing",
            parameters={"type": "object", "properties": {}},
            hidden=False,
        )
        async def _test_no_examples_tool():
            return ToolResult(success=True, data="ok")

        try:
            result = await help_me()

            assert result.success is True
            # Find the test tool in the output
            test_tool_data = next(
                (t for t in result.data["tools"] if t["name"] == "_test_no_examples_tool"),
                None,
            )
            assert test_tool_data is not None
            assert test_tool_data["examples"] == []
        finally:
            # Clean up the global registry
            del tool_registry._tools["_test_no_examples_tool"]
