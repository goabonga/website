# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for ChatOrchestrator."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.chat.orchestrator import (
    SUMMARY_CONTEXT_TEMPLATE,
    SYSTEM_PROMPT,
    TOOL_CONTEXT_TEMPLATE,
    ChatOrchestrator,
)


@pytest.fixture(autouse=True)
def _suppress_background_tasks(monkeypatch):
    """Prevent asyncio.create_task from launching unawaited coroutines in tests."""

    def _noop_create_task(coro, **kwargs):
        # Close the coroutine to avoid 'was never awaited' warnings
        coro.close()
        # Return a finished future to keep callers happy
        future = asyncio.get_event_loop().create_future()
        future.set_result(None)
        return future

    monkeypatch.setattr(asyncio, "create_task", _noop_create_task)


@pytest.fixture
def mock_session():
    """Return a mocked AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def user_id():
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def session_id():
    return "abcdef12-3456-7890-abcd-ef1234567890"


@pytest.fixture
def conversation_id():
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def mock_conversation(conversation_id, user_id):
    """Return a mock Conversation object."""
    conv = MagicMock()
    conv.id = conversation_id
    conv.user_id = user_id
    conv.session_id = None
    conv.title = "Test Conversation"
    conv.summary = "A test summary."
    conv.archived_at = None
    conv.messages = []
    return conv


@pytest.fixture
def orchestrator(mock_session):
    """Return a ChatOrchestrator with all dependencies mocked."""
    with (
        patch("backend.chat.orchestrator.OpenAIClient") as mock_client_cls,
        patch("backend.chat.orchestrator.ChatService") as mock_service_cls,
        patch("backend.chat.orchestrator.KnowledgeBase") as mock_kb_cls,
        patch("backend.chat.orchestrator.PromptService") as mock_prompt_cls,
    ):
        mock_client = AsyncMock()
        mock_service = AsyncMock()
        mock_kb = AsyncMock()
        mock_prompt = AsyncMock()

        mock_client_cls.return_value = mock_client
        mock_service_cls.return_value = mock_service
        mock_kb_cls.return_value = mock_kb
        mock_prompt_cls.return_value = mock_prompt

        orch = ChatOrchestrator(mock_session)

        # Expose mocks for test assertions
        orch.client = mock_client
        orch.chat_service = mock_service
        orch.knowledge_base = mock_kb
        orch.prompt_service = mock_prompt

        yield orch


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------


async def test_build_messages_all_parameters(orchestrator):
    """_build_messages with all parameters includes system, summary, context, history."""
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]
    result = orchestrator._build_messages(
        message="What is X?",
        history=history,
        context="Some RAG context",
        summary="Previous summary",
        system_prompt="Custom prompt",
    )

    assert result[0] == {"role": "system", "content": "Custom prompt"}
    assert result[1] == {
        "role": "system",
        "content": SUMMARY_CONTEXT_TEMPLATE.format(summary="Previous summary"),
    }
    assert result[2] == {
        "role": "system",
        "content": TOOL_CONTEXT_TEMPLATE.format(context="Some RAG context"),
    }
    assert result[3] == {"role": "user", "content": "Hi"}
    assert result[4] == {"role": "assistant", "content": "Hello!"}
    assert result[5] == {"role": "user", "content": "What is X?"}


async def test_build_messages_no_summary_no_context(orchestrator):
    """_build_messages with no summary and no context uses defaults."""
    result = orchestrator._build_messages(
        message="Hello",
        history=[],
        context="",
        summary=None,
        system_prompt=None,
    )

    # Default system prompt, no summary message, no context message (empty string is falsy)
    assert result[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert result[1] == {"role": "user", "content": "Hello"}
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _format_tool_results
# ---------------------------------------------------------------------------


async def test_format_tool_results(orchestrator):
    """_format_tool_results formats success and failure."""
    results = [
        {"tool": "search", "success": True, "data": "found it", "error": None},
        {"tool": "calc", "success": False, "data": None, "error": "division by zero"},
    ]
    formatted = orchestrator._format_tool_results(results)

    assert "Tool 'search' returned: found it" in formatted
    assert "Tool 'calc' failed: division by zero" in formatted


# ---------------------------------------------------------------------------
# _should_update_title
# ---------------------------------------------------------------------------


async def test_should_update_title_first_exchange(orchestrator):
    """_should_update_title returns True for first exchange (<=2 messages)."""
    assert orchestrator._should_update_title(1) is True
    assert orchestrator._should_update_title(2) is True


async def test_should_update_title_at_interval(orchestrator):
    """_should_update_title returns True at the correct interval."""
    # TITLE_UPDATE_INTERVAL = 5
    # user_message_count = message_count // 2
    # Triggers when user_message_count % 5 == 0
    # user_message_count=5 -> message_count=10
    assert orchestrator._should_update_title(10) is True


async def test_should_update_title_false_otherwise(orchestrator):
    """_should_update_title returns False for non-interval counts."""
    assert orchestrator._should_update_title(4) is False
    assert orchestrator._should_update_title(6) is False
    assert orchestrator._should_update_title(8) is False


# ---------------------------------------------------------------------------
# _should_update_summary
# ---------------------------------------------------------------------------


async def test_should_update_summary_false_for_few_messages(orchestrator):
    """_should_update_summary returns False for < 4 messages."""
    assert orchestrator._should_update_summary(1) is False
    assert orchestrator._should_update_summary(2) is False
    assert orchestrator._should_update_summary(3) is False


async def test_should_update_summary_true_at_interval(orchestrator):
    """_should_update_summary returns True at the correct interval."""
    # SUMMARY_UPDATE_INTERVAL = 3
    # user_message_count = (message_count + 1) // 2
    # Triggers when user_message_count % 3 == 0
    # user_message_count=3 -> message_count=5 -> (5+1)//2=3
    assert orchestrator._should_update_summary(5) is True


# ---------------------------------------------------------------------------
# process_message - tool results path
# ---------------------------------------------------------------------------


async def test_process_message_with_tool_results(
    orchestrator, user_id, session_id, conversation_id, mock_conversation
):
    """process_message with tool results returns tool_call intent."""
    orchestrator.chat_service.get_conversation.return_value = None
    orchestrator.chat_service.create_conversation.return_value = mock_conversation
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    tool_results = [
        {
            "tool": "search",
            "arguments": {"q": "test"},
            "success": True,
            "data": "result",
            "error": None,
            "save_in_history": True,
        }
    ]

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = tool_results
        orchestrator.client.chat.return_value = {
            "content": "Here is the answer.",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        result = await orchestrator.process_message(
            message="search for something",
            user_id=user_id,
            session_id=session_id,
        )

    assert result["intent"] == "tool_call"
    assert result["tool_results"] == tool_results
    assert result["content"] == "Here is the answer."
    assert result["conversation_id"] == str(conversation_id)


# ---------------------------------------------------------------------------
# process_message - no results (fallback)
# ---------------------------------------------------------------------------


async def test_process_message_no_results(
    orchestrator, user_id, session_id, conversation_id, mock_conversation
):
    """process_message with no tool results generates persona response."""
    orchestrator.chat_service.get_conversation.return_value = None
    orchestrator.chat_service.create_conversation.return_value = mock_conversation
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = "You are a helpful assistant."

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = []  # No tools

        orchestrator.client.chat.return_value = {
            "content": "I can help with specific topics.",
            "usage": {"prompt_tokens": 20, "completion_tokens": 8},
        }

        result = await orchestrator.process_message(
            message="What is the weather?",
            user_id=user_id,
            session_id=session_id,
        )

    assert result["intent"] == "no_match"
    assert result["content"] == "I can help with specific topics."
    assert result["tool_results"] is None
    assert result["usage"]["prompt_tokens"] == 20
    assert result["usage"]["completion_tokens"] == 8


# ---------------------------------------------------------------------------
# process_message_stream - tool path
# ---------------------------------------------------------------------------


async def test_process_message_stream_tool_path(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream yields history, intent, tools, tokens, done for tool path."""
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = [
        {"role": "user", "content": "prior message"}
    ]
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    tool_results = [
        {
            "tool": "search",
            "arguments": {},
            "success": True,
            "data": "found",
            "error": None,
            "save_in_history": True,
        }
    ]

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = tool_results

        # Mock streaming
        async def mock_stream(messages):
            yield {"type": "token", "content": "Hello"}
            yield {"type": "token", "content": " world"}
            yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 5}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Do a search",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert event_types[0] == "history"
    assert event_types[1] == "intent"
    assert events[1]["intent"] == "tool_call"
    assert event_types[2] == "tools"
    assert events[2]["results"] == tool_results
    assert "token" in event_types
    assert event_types[-1] == "done"


# ---------------------------------------------------------------------------
# process_message_stream - no_match path
# ---------------------------------------------------------------------------


async def test_process_message_stream_no_match_path(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream yields history, intent, tokens, done for no_match path."""
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = "You are a helpful assistant."

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = []  # No tools

        async def mock_stream(messages):
            yield {"type": "token", "content": "I can help"}
            yield {"type": "token", "content": " with topics."}
            yield {"type": "usage", "prompt_tokens": 15, "completion_tokens": 6}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="What is the weather?",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert event_types[0] == "history"
    assert event_types[1] == "intent"
    assert events[1]["intent"] == "no_match"
    assert "token" in event_types
    assert event_types[-1] == "done"


# ---------------------------------------------------------------------------
# _enhance_tools_with_namespaces
# ---------------------------------------------------------------------------


async def test_enhance_tools_injects_enum_and_description(orchestrator):
    """_enhance_tools_with_namespaces adds enum and description to namespace param."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "Search the knowledge base",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "query"},
                        "namespace": {
                            "type": "string",
                            "description": "Optional namespace",
                        },
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    ns1 = MagicMock()
    ns1.slug = "faq"
    ns1.name = "FAQ"
    ns1.description = "Frequently asked questions"
    ns2 = MagicMock()
    ns2.slug = "docs"
    ns2.name = "Documentation"
    ns2.description = None

    orchestrator.knowledge_base.list_namespaces.return_value = [ns1, ns2]

    result = await orchestrator._enhance_tools_with_namespaces(tools, {"openid"})

    ns_param = result[0]["function"]["parameters"]["properties"]["namespace"]
    assert ns_param["enum"] == ["faq", "docs"]
    assert "faq: FAQ" in ns_param["description"]
    assert "docs: Documentation" in ns_param["description"]
    assert "Frequently asked questions" in ns_param["description"]


async def test_enhance_tools_no_namespaces_is_noop(orchestrator):
    """_enhance_tools_with_namespaces is a no-op when no namespaces exist."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "Search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "namespace": {"type": "string", "description": "Optional"},
                    },
                },
            },
        }
    ]

    orchestrator.knowledge_base.list_namespaces.return_value = []

    result = await orchestrator._enhance_tools_with_namespaces(tools, None)

    ns_param = result[0]["function"]["parameters"]["properties"]["namespace"]
    assert "enum" not in ns_param


async def test_enhance_tools_no_search_knowledge_is_noop(orchestrator):
    """_enhance_tools_with_namespaces does nothing when search_knowledge is absent."""
    tools = [
        {
            "type": "function",
            "function": {"name": "other_tool", "description": "Other", "parameters": {}},
        }
    ]

    ns = MagicMock()
    ns.slug = "faq"
    ns.name = "FAQ"
    ns.description = None
    orchestrator.knowledge_base.list_namespaces.return_value = [ns]

    result = await orchestrator._enhance_tools_with_namespaces(tools, {"openid"})

    assert result[0]["function"]["name"] == "other_tool"


async def test_enhance_tools_no_namespace_param_is_noop(orchestrator):
    """_enhance_tools_with_namespaces is a no-op when namespace property is missing."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "Search",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        }
    ]

    ns = MagicMock()
    ns.slug = "faq"
    ns.name = "FAQ"
    ns.description = None
    orchestrator.knowledge_base.list_namespaces.return_value = [ns]

    result = await orchestrator._enhance_tools_with_namespaces(tools, {"openid"})

    assert "namespace" not in result[0]["function"]["parameters"]["properties"]


async def test_enhance_tools_does_not_mutate_registry(orchestrator):
    """_enhance_tools_with_namespaces does not mutate the original Tool.parameters."""
    from backend.llm.tools import tool_registry

    original_tool = tool_registry.get_tool("search_knowledge")
    original_desc = original_tool.parameters["properties"]["namespace"]["description"]

    tools = tool_registry.get_openai_tools({"openid"})

    ns = MagicMock()
    ns.slug = "test-ns"
    ns.name = "Test"
    ns.description = "Test namespace"
    orchestrator.knowledge_base.list_namespaces.return_value = [ns]

    await orchestrator._enhance_tools_with_namespaces(tools, {"openid"})

    current_tool = tool_registry.get_tool("search_knowledge")
    assert "enum" not in current_tool.parameters["properties"]["namespace"]
    assert current_tool.parameters["properties"]["namespace"]["description"] == original_desc


# ---------------------------------------------------------------------------
# _try_execute_tools
# ---------------------------------------------------------------------------


async def test_try_execute_tools_no_tools(orchestrator, user_id, session_id, conversation_id):
    """_try_execute_tools returns [] when no tools are available."""
    from backend.llm.tools import ToolContext

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = []

        result = await orchestrator._try_execute_tools(
            message="test", history=[], tool_context=tool_context
        )

    assert result == []


async def test_try_execute_tools_no_tool_calls(orchestrator, user_id, session_id, conversation_id):
    """_try_execute_tools returns [] when LLM returns no tool calls."""
    from backend.llm.tools import ToolContext

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "search", "description": "search", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {"content": "no tools needed", "tool_calls": []}

        result = await orchestrator._try_execute_tools(
            message="hello", history=[], tool_context=tool_context
        )

    assert result == []


async def test_try_execute_tools_with_tool_calls(
    orchestrator, user_id, session_id, conversation_id
):
    """_try_execute_tools executes tools and returns results."""
    from backend.llm.tools import ToolContext, ToolResult

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    mock_tool = MagicMock()
    mock_tool.save_in_history = True

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "search", "description": "search", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {
            "content": "",
            "tool_calls": [{"name": "search", "arguments": {"q": "test"}}],
        }
        mock_registry.execute = AsyncMock(
            return_value=ToolResult(success=True, data="found it", error=None)
        )
        mock_registry.get_tool.return_value = mock_tool

        result = await orchestrator._try_execute_tools(
            message="search for something", history=[], tool_context=tool_context
        )

    assert len(result) == 1
    assert result[0]["tool"] == "search"
    assert result[0]["success"] is True
    assert result[0]["data"] == "found it"
    assert result[0]["save_in_history"] is True


async def test_try_execute_tools_with_failed_tool(
    orchestrator, user_id, session_id, conversation_id
):
    """_try_execute_tools handles failed tool execution."""
    from backend.llm.tools import ToolContext, ToolResult

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    mock_tool = MagicMock()
    mock_tool.save_in_history = True

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "search", "description": "search", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {
            "content": "",
            "tool_calls": [{"name": "search", "arguments": {"q": "bad"}}],
        }
        mock_registry.execute = AsyncMock(
            return_value=ToolResult(success=False, data=None, error="not found")
        )
        mock_registry.get_tool.return_value = mock_tool

        result = await orchestrator._try_execute_tools(
            message="search for something bad", history=[], tool_context=tool_context
        )

    assert len(result) == 1
    assert result[0]["success"] is False
    assert result[0]["error"] == "not found"


# ---------------------------------------------------------------------------
# _execute_tools (legacy)
# ---------------------------------------------------------------------------


async def test_execute_tools_no_tools(orchestrator):
    """_execute_tools returns [] when no tools are available."""
    from backend.llm.tools import ToolContext

    tool_context = ToolContext(scopes={"openid"})

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = []

        result = await orchestrator._execute_tools(
            message="test", history=[], tool_context=tool_context
        )

    assert result == []


async def test_execute_tools_no_tool_calls(orchestrator):
    """_execute_tools returns [] when LLM returns no tool calls."""
    from backend.llm.tools import ToolContext

    tool_context = ToolContext(scopes={"openid"})

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "calc", "description": "calc", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {"content": "no tools", "tool_calls": []}

        result = await orchestrator._execute_tools(
            message="hello", history=[], tool_context=tool_context
        )

    assert result == []


async def test_execute_tools_with_tool_calls(orchestrator, user_id, session_id, conversation_id):
    """_execute_tools executes tools and returns results (legacy path)."""
    from backend.llm.tools import ToolContext, ToolResult

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    mock_tool = MagicMock()
    mock_tool.save_in_history = False

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "calc", "description": "calc", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {
            "content": "",
            "tool_calls": [{"name": "calc", "arguments": {"expr": "1+1"}}],
        }
        mock_registry.execute = AsyncMock(
            return_value=ToolResult(success=False, data=None, error="division by zero")
        )
        mock_registry.get_tool.return_value = mock_tool

        result = await orchestrator._execute_tools(
            message="calculate something", history=[], tool_context=tool_context
        )

    assert len(result) == 1
    assert result[0]["tool"] == "calc"
    assert result[0]["success"] is False
    assert result[0]["error"] == "division by zero"
    assert result[0]["save_in_history"] is False


async def test_execute_tools_with_successful_tool(
    orchestrator, user_id, session_id, conversation_id
):
    """_execute_tools handles successful tool execution (legacy path)."""
    from backend.llm.tools import ToolContext, ToolResult

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    mock_tool = MagicMock()
    mock_tool.save_in_history = True

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "calc", "description": "calc", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {
            "content": "",
            "tool_calls": [{"name": "calc", "arguments": {"expr": "1+1"}}],
        }
        mock_registry.execute = AsyncMock(
            return_value=ToolResult(success=True, data="2", error=None)
        )
        mock_registry.get_tool.return_value = mock_tool

        result = await orchestrator._execute_tools(
            message="calculate 1+1", history=[], tool_context=tool_context
        )

    assert len(result) == 1
    assert result[0]["tool"] == "calc"
    assert result[0]["success"] is True
    assert result[0]["data"] == "2"


# ---------------------------------------------------------------------------
# _generate_title
# ---------------------------------------------------------------------------


async def test_generate_title_success(orchestrator):
    """_generate_title returns the generated title."""
    orchestrator.client.chat.return_value = {"content": "  My Cool Title  "}

    title = await orchestrator._generate_title(
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
    )

    assert title == "My Cool Title"
    orchestrator.client.chat.assert_awaited_once()


async def test_generate_title_empty_response(orchestrator):
    """_generate_title returns 'New conversation' for empty response."""
    orchestrator.client.chat.return_value = {"content": ""}

    title = await orchestrator._generate_title(
        [
            {"role": "user", "content": "Hello"},
        ]
    )

    assert title == "New conversation"


async def test_generate_title_exception(orchestrator):
    """_generate_title returns 'New conversation' on exception."""
    orchestrator.client.chat.side_effect = RuntimeError("API error")

    title = await orchestrator._generate_title(
        [
            {"role": "user", "content": "Hello"},
        ]
    )

    assert title == "New conversation"


# ---------------------------------------------------------------------------
# _generate_summary
# ---------------------------------------------------------------------------


async def test_generate_summary_success(orchestrator):
    """_generate_summary returns the generated summary."""
    orchestrator.client.chat.return_value = {"content": "  A concise summary.  "}

    summary = await orchestrator._generate_summary(
        history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        previous_summary="Old summary",
    )

    assert summary == "A concise summary."
    orchestrator.client.chat.assert_awaited_once()


async def test_generate_summary_empty_response(orchestrator):
    """_generate_summary returns previous_summary for empty response."""
    orchestrator.client.chat.return_value = {"content": ""}

    summary = await orchestrator._generate_summary(
        history=[{"role": "user", "content": "Hello"}],
        previous_summary="Old summary",
    )

    assert summary == "Old summary"


async def test_generate_summary_empty_response_no_previous(orchestrator):
    """_generate_summary returns '' when empty response and no previous summary."""
    orchestrator.client.chat.return_value = {"content": ""}

    summary = await orchestrator._generate_summary(
        history=[{"role": "user", "content": "Hello"}],
        previous_summary=None,
    )

    assert summary == ""


async def test_generate_summary_exception(orchestrator):
    """_generate_summary returns previous_summary on exception."""
    orchestrator.client.chat.side_effect = RuntimeError("API error")

    summary = await orchestrator._generate_summary(
        history=[{"role": "user", "content": "Hello"}],
        previous_summary="Existing summary",
    )

    assert summary == "Existing summary"


async def test_generate_summary_exception_no_previous(orchestrator):
    """_generate_summary returns '' on exception when no previous summary."""
    orchestrator.client.chat.side_effect = RuntimeError("API error")

    summary = await orchestrator._generate_summary(
        history=[{"role": "user", "content": "Hello"}],
        previous_summary=None,
    )

    assert summary == ""


# ---------------------------------------------------------------------------
# _update_title_background
# ---------------------------------------------------------------------------


async def test_update_title_background(orchestrator, conversation_id, user_id, session_id):
    """_update_title_background generates title and updates via new session."""
    orchestrator.client.chat.return_value = {"content": "Generated Title"}

    mock_bg_session = AsyncMock()
    mock_bg_chat_service = AsyncMock()

    with (
        patch("backend.chat.orchestrator.async_session_maker") as mock_session_maker,
        patch("backend.chat.orchestrator.ChatService") as mock_chat_cls,
    ):
        # Make async_session_maker work as an async context manager
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_bg_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_chat_cls.return_value = mock_bg_chat_service

        await orchestrator._update_title_background(
            conversation_id=conversation_id,
            history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ],
            user_id=user_id,
            session_id=session_id,
        )

    mock_bg_chat_service.update_title.assert_awaited_once_with(
        conversation_id, "Generated Title", user_id, session_id
    )


async def test_update_title_background_exception(
    orchestrator, conversation_id, user_id, session_id
):
    """_update_title_background logs warning on DB failure and does not raise."""
    orchestrator.client.chat.return_value = {"content": "Title"}

    with patch("backend.chat.orchestrator.async_session_maker") as mock_session_maker:
        # Make the async context manager raise when entered
        mock_session_maker.return_value.__aenter__ = AsyncMock(
            side_effect=RuntimeError("DB connection failed")
        )
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        # Should not raise despite the DB error
        await orchestrator._update_title_background(
            conversation_id=conversation_id,
            history=[{"role": "user", "content": "Hello"}],
            user_id=user_id,
            session_id=session_id,
        )


# ---------------------------------------------------------------------------
# _update_summary_background
# ---------------------------------------------------------------------------


async def test_update_summary_background(orchestrator, conversation_id, user_id, session_id):
    """_update_summary_background generates summary and updates via new session."""
    orchestrator.client.chat.return_value = {"content": "New summary"}

    mock_bg_session = AsyncMock()
    mock_bg_chat_service = AsyncMock()

    with (
        patch("backend.chat.orchestrator.async_session_maker") as mock_session_maker,
        patch("backend.chat.orchestrator.ChatService") as mock_chat_cls,
    ):
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_bg_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_chat_cls.return_value = mock_bg_chat_service

        await orchestrator._update_summary_background(
            conversation_id=conversation_id,
            history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ],
            previous_summary="Old summary",
            user_id=user_id,
            session_id=session_id,
        )

    mock_bg_chat_service.update_summary.assert_awaited_once_with(
        conversation_id, "New summary", user_id, session_id
    )


async def test_update_summary_background_exception(
    orchestrator, conversation_id, user_id, session_id
):
    """_update_summary_background logs warning on DB failure and does not raise."""
    orchestrator.client.chat.return_value = {"content": "New summary"}

    with patch("backend.chat.orchestrator.async_session_maker") as mock_session_maker:
        # Make the async context manager raise when entered
        mock_session_maker.return_value.__aenter__ = AsyncMock(
            side_effect=RuntimeError("DB connection failed")
        )
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        # Should not raise despite the DB error
        await orchestrator._update_summary_background(
            conversation_id=conversation_id,
            history=[{"role": "user", "content": "Hello"}],
            previous_summary=None,
            user_id=user_id,
            session_id=session_id,
        )


# ---------------------------------------------------------------------------
# process_message - get existing conversation
# ---------------------------------------------------------------------------


async def test_process_message_get_existing_conversation(
    orchestrator, user_id, session_id, conversation_id, mock_conversation
):
    """process_message uses conversation_id to get existing conversation."""
    orchestrator.chat_service.get_conversation.return_value = mock_conversation
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = []

        orchestrator.client.chat.return_value = {
            "content": "Hello!",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        result = await orchestrator.process_message(
            message="Hello",
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=session_id,
        )

    # Should have called get_conversation (not create_conversation)
    orchestrator.chat_service.get_conversation.assert_awaited_once_with(
        conversation_id, user_id, session_id
    )
    orchestrator.chat_service.create_conversation.assert_not_awaited()
    assert result["conversation_id"] == str(conversation_id)


async def test_process_message_get_nonexistent_conversation_creates_new(
    orchestrator, user_id, session_id, conversation_id, mock_conversation
):
    """process_message creates new conversation when conversation_id not found."""
    orchestrator.chat_service.get_conversation.return_value = None
    orchestrator.chat_service.create_conversation.return_value = mock_conversation
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = []

        orchestrator.client.chat.return_value = {
            "content": "Hello!",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        await orchestrator.process_message(
            message="Hello",
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=session_id,
        )

    orchestrator.chat_service.get_conversation.assert_awaited_once()
    orchestrator.chat_service.create_conversation.assert_awaited_once_with(user_id, session_id)


# ---------------------------------------------------------------------------
# _log_context
# ---------------------------------------------------------------------------


async def test_log_context_with_values(orchestrator, user_id, session_id):
    """_log_context returns dict with truncated session_id and stringified user_id."""
    result = orchestrator._log_context(user_id, session_id)

    assert result["user_id"] == str(user_id)
    assert result["session_id"] == session_id[:8]


async def test_log_context_with_none_values(orchestrator):
    """_log_context returns dict with None for missing user_id and session_id."""
    result = orchestrator._log_context(None, None)

    assert result["user_id"] is None
    assert result["session_id"] is None


# ---------------------------------------------------------------------------
# process_message - conversation_id provided + found / not found (lines 132-146)
# ---------------------------------------------------------------------------


async def test_process_message_conversation_id_found_uses_existing(
    orchestrator, user_id, session_id, conversation_id, mock_conversation
):
    """process_message with conversation_id that exists uses it and reads summary."""
    mock_conversation.summary = "DB summary"
    orchestrator.chat_service.get_conversation.return_value = mock_conversation
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = []

        orchestrator.client.chat.return_value = {
            "content": "Hello!",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        result = await orchestrator.process_message(
            message="Hello",
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=session_id,
        )

    orchestrator.chat_service.get_conversation.assert_awaited_once_with(
        conversation_id, user_id, session_id
    )
    orchestrator.chat_service.create_conversation.assert_not_awaited()
    assert result["conversation_id"] == str(conversation_id)


async def test_process_message_conversation_id_not_found_creates_new(
    orchestrator, user_id, session_id, conversation_id, mock_conversation
):
    """process_message creates new conversation when provided conversation_id is not found."""
    orchestrator.chat_service.get_conversation.return_value = None
    orchestrator.chat_service.create_conversation.return_value = mock_conversation
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = []

        orchestrator.client.chat.return_value = {
            "content": "Hello!",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        result = await orchestrator.process_message(
            message="Hello",
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=session_id,
        )

    orchestrator.chat_service.get_conversation.assert_awaited_once_with(
        conversation_id, user_id, session_id
    )
    orchestrator.chat_service.create_conversation.assert_awaited_once_with(user_id, session_id)
    assert result["conversation_id"] == str(mock_conversation.id)


# ---------------------------------------------------------------------------
# process_message - history retrieval branch (lines 150-153)
# ---------------------------------------------------------------------------


async def test_process_message_retrieves_history_when_save_and_conversation_id(
    orchestrator, user_id, session_id, conversation_id, mock_conversation
):
    """process_message fetches history when save_history=True and conversation_id exists."""
    orchestrator.chat_service.get_conversation.return_value = mock_conversation
    orchestrator.chat_service.get_conversation_history.return_value = [
        {"role": "user", "content": "old msg"},
        {"role": "assistant", "content": "old response"},
    ]
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = []

        orchestrator.client.chat.return_value = {
            "content": "Response",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        await orchestrator.process_message(
            message="New msg",
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=session_id,
        )

    orchestrator.chat_service.get_conversation_history.assert_awaited_once_with(
        conversation_id, limit=20
    )


# ---------------------------------------------------------------------------
# process_message_stream - tool path: save_in_history=False (lines 353->356)
# ---------------------------------------------------------------------------


async def test_process_message_stream_tool_save_in_history_false(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream tool path skips history when all tools have save_in_history=False."""
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    tool_results = [
        {
            "tool": "ephemeral",
            "arguments": {},
            "success": True,
            "data": "ok",
            "error": None,
            "save_in_history": False,
        }
    ]

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = tool_results

        async def mock_stream(messages):
            yield {"type": "token", "content": "Response"}
            yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 5}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Do something",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert "done" in event_types
    # No messages saved when save_in_history=False
    orchestrator.chat_service.add_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# process_message_stream - tool path: content + title/summary (lines 368-402)
# ---------------------------------------------------------------------------


async def test_process_message_stream_tool_path_content_title_summary(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream tool path saves messages and triggers title on first exchange."""
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    # Empty history + 2 new = 2 => _should_update_title(2)=True
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    tool_results = [
        {
            "tool": "search",
            "arguments": {},
            "success": True,
            "data": "found",
            "error": None,
            "save_in_history": True,
        }
    ]

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = tool_results

        async def mock_stream(messages):
            yield {"type": "token", "content": "Hello"}
            yield {"type": "token", "content": " world"}
            yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 5}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Do a search",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    orchestrator.chat_service.add_message.assert_any_await(
        mock_conversation.id, "user", "Do a search"
    )
    orchestrator.chat_service.add_message.assert_any_await(
        mock_conversation.id, "assistant", "Hello world"
    )
    done_event = [e for e in events if e["type"] == "done"][0]
    assert done_event["usage"]["prompt_tokens"] == 10
    assert done_event["usage"]["completion_tokens"] == 5


async def test_process_message_stream_tool_path_summary_update(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream tool path triggers summary update at correct message count."""
    # history=3 + 2 new = 5 => _should_update_summary(5)=True
    existing_history = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "resp1"},
        {"role": "user", "content": "msg2"},
    ]
    mock_conversation.summary = "Old summary"
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = existing_history
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    tool_results = [
        {
            "tool": "search",
            "arguments": {},
            "success": True,
            "data": "found",
            "error": None,
            "save_in_history": True,
        }
    ]

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = tool_results

        async def mock_stream(messages):
            yield {"type": "token", "content": "Response"}
            yield {"type": "usage", "prompt_tokens": 5, "completion_tokens": 3}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Search query",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    orchestrator.chat_service.add_message.assert_any_await(
        mock_conversation.id, "assistant", "Response"
    )


# ---------------------------------------------------------------------------
# process_message_stream - no_match path: title/summary (lines 521-537)
# ---------------------------------------------------------------------------


async def test_process_message_stream_no_match_path_title_update(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream no_match path triggers title update on first exchange."""
    # Empty history + 2 new = 2 => _should_update_title(2)=True
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = "You are a helpful assistant."

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = []

        async def mock_stream(messages):
            yield {"type": "token", "content": "Persona response"}
            yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 4}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Random question",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    # User message and persona response saved
    orchestrator.chat_service.add_message.assert_any_await(
        mock_conversation.id, "user", "Random question"
    )
    orchestrator.chat_service.add_message.assert_any_await(
        mock_conversation.id, "assistant", "Persona response"
    )

    done_event = [e for e in events if e["type"] == "done"][0]
    assert done_event["conversation_id"] == str(mock_conversation.id)


async def test_process_message_stream_no_match_path_summary_update(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream no_match path triggers summary update at correct count."""
    # history=3 + 2 new = 5 => _should_update_summary(5)=True
    existing_history = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "resp1"},
        {"role": "user", "content": "msg2"},
    ]
    mock_conversation.summary = "Old summary"
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = existing_history
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = "You are a helpful assistant."

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = []

        async def mock_stream(messages):
            yield {"type": "token", "content": "Response"}
            yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 3}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Off-topic question",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    assert events[-1]["type"] == "done"
    orchestrator.chat_service.add_message.assert_any_await(
        mock_conversation.id, "user", "Off-topic question"
    )


# ---------------------------------------------------------------------------
# _try_execute_tools - multiple calls mixed results
# ---------------------------------------------------------------------------


async def test_try_execute_tools_multiple_calls_mixed_results(
    orchestrator, user_id, session_id, conversation_id
):
    """_try_execute_tools handles multiple tool calls with success and failure."""
    from backend.llm.tools import ToolContext, ToolResult

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    mock_tool_ok = MagicMock()
    mock_tool_ok.save_in_history = True
    mock_tool_fail = MagicMock()
    mock_tool_fail.save_in_history = False

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {"type": "function", "function": {"name": "a", "description": "a", "parameters": {}}},
            {"type": "function", "function": {"name": "b", "description": "b", "parameters": {}}},
        ]
        orchestrator.client.chat.return_value = {
            "content": "",
            "tool_calls": [
                {"name": "a", "arguments": {"q": "test"}},
                {"name": "b", "arguments": {"expr": "1/0"}},
            ],
        }
        mock_registry.execute = AsyncMock(
            side_effect=[
                ToolResult(success=True, data="ok", error=None),
                ToolResult(success=False, data=None, error="division by zero"),
            ]
        )
        mock_registry.get_tool.side_effect = [mock_tool_ok, mock_tool_fail]

        result = await orchestrator._try_execute_tools(
            message="run both", history=[], tool_context=tool_context
        )

    assert len(result) == 2
    assert result[0]["success"] is True
    assert result[0]["save_in_history"] is True
    assert result[1]["success"] is False
    assert result[1]["save_in_history"] is False


# ---------------------------------------------------------------------------
# _execute_tools - tool_context=None (line 632)
# ---------------------------------------------------------------------------


async def test_execute_tools_tool_context_none(orchestrator):
    """_execute_tools handles tool_context=None for scopes extraction."""
    from backend.llm.tools import ToolResult

    mock_tool = MagicMock()
    mock_tool.save_in_history = True

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "search", "description": "s", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {
            "content": "",
            "tool_calls": [{"name": "search", "arguments": {"q": "test"}}],
        }
        mock_registry.execute = AsyncMock(
            return_value=ToolResult(success=True, data="found", error=None)
        )
        mock_registry.get_tool.return_value = mock_tool

        result = await orchestrator._execute_tools(message="search", history=[], tool_context=None)

    mock_registry.get_openai_tools.assert_called_once_with(None)
    assert len(result) == 1
    assert result[0]["success"] is True


async def test_execute_tools_tool_not_in_registry(
    orchestrator, user_id, session_id, conversation_id
):
    """_execute_tools defaults save_in_history=True when tool is not found in registry."""
    from backend.llm.tools import ToolContext, ToolResult

    tool_context = ToolContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        is_authenticated=True,
        scopes={"openid"},
    )

    with patch("backend.chat.orchestrator.tool_registry") as mock_registry:
        mock_registry.get_openai_tools.return_value = [
            {
                "type": "function",
                "function": {"name": "unknown", "description": "u", "parameters": {}},
            }
        ]
        orchestrator.client.chat.return_value = {
            "content": "",
            "tool_calls": [{"name": "unknown", "arguments": {}}],
        }
        mock_registry.execute = AsyncMock(
            return_value=ToolResult(success=True, data="ok", error=None)
        )
        # get_tool returns None => save_in_history defaults to True
        mock_registry.get_tool.return_value = None

        result = await orchestrator._execute_tools(
            message="run unknown", history=[], tool_context=tool_context
        )

    assert len(result) == 1
    assert result[0]["save_in_history"] is True


# ---------------------------------------------------------------------------
# _generate_title - strips quotes, truncates (lines 756-774)
# ---------------------------------------------------------------------------


async def test_generate_title_strips_quotes(orchestrator):
    """_generate_title strips surrounding quotes from title."""
    orchestrator.client.chat.return_value = {"content": '"My Title"'}

    title = await orchestrator._generate_title(
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
    )

    assert title == "My Title"


async def test_generate_title_truncates_long(orchestrator):
    """_generate_title truncates titles longer than 100 characters."""
    orchestrator.client.chat.return_value = {"content": "A" * 150}

    title = await orchestrator._generate_title(
        [
            {"role": "user", "content": "Hello"},
        ]
    )

    assert len(title) <= 100


# ---------------------------------------------------------------------------
# _generate_summary - prompt construction (lines 822-848)
# ---------------------------------------------------------------------------


async def test_generate_summary_without_previous_summary(orchestrator):
    """_generate_summary uses 'No previous summary.' when previous is None."""
    orchestrator.client.chat.return_value = {"content": "New summary"}

    summary = await orchestrator._generate_summary(
        history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ],
        previous_summary=None,
    )

    assert summary == "New summary"
    call_args = orchestrator.client.chat.call_args
    messages = call_args[0][0]
    assert "No previous summary." in messages[0]["content"]


async def test_generate_summary_with_previous_summary_in_prompt(orchestrator):
    """_generate_summary includes previous summary text in prompt."""
    orchestrator.client.chat.return_value = {"content": "Updated summary"}

    summary = await orchestrator._generate_summary(
        history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ],
        previous_summary="Old context",
    )

    assert summary == "Updated summary"
    call_args = orchestrator.client.chat.call_args
    messages = call_args[0][0]
    assert "Old context" in messages[0]["content"]


# ---------------------------------------------------------------------------
# _update_title_background - both success and exception paths (lines 803-813)
# ---------------------------------------------------------------------------


async def test_update_title_background_llm_failure(
    orchestrator, conversation_id, user_id, session_id
):
    """_update_title_background handles LLM failure without raising."""
    orchestrator.client.chat.side_effect = RuntimeError("LLM down")

    await orchestrator._update_title_background(
        conversation_id=conversation_id,
        history=[{"role": "user", "content": "Hello"}],
        user_id=user_id,
        session_id=session_id,
    )


async def test_update_title_background_db_failure(
    orchestrator, conversation_id, user_id, session_id
):
    """_update_title_background handles DB failure without raising."""
    orchestrator.client.chat.return_value = {"content": "Title"}

    with patch("backend.chat.orchestrator.async_session_maker") as mock_sm:
        mock_sm.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)

        await orchestrator._update_title_background(
            conversation_id=conversation_id,
            history=[{"role": "user", "content": "Hello"}],
            user_id=user_id,
            session_id=session_id,
        )


# ---------------------------------------------------------------------------
# _update_summary_background - both success and exception paths (lines 872-882)
# ---------------------------------------------------------------------------


async def test_update_summary_background_llm_failure(
    orchestrator, conversation_id, user_id, session_id
):
    """_update_summary_background handles LLM failure without raising."""
    orchestrator.client.chat.side_effect = RuntimeError("LLM down")

    await orchestrator._update_summary_background(
        conversation_id=conversation_id,
        history=[{"role": "user", "content": "Hello"}],
        previous_summary=None,
        user_id=user_id,
        session_id=session_id,
    )


async def test_update_summary_background_db_failure(
    orchestrator, conversation_id, user_id, session_id
):
    """_update_summary_background handles DB failure without raising."""
    orchestrator.client.chat.return_value = {"content": "Summary"}

    with patch("backend.chat.orchestrator.async_session_maker") as mock_sm:
        mock_sm.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)

        await orchestrator._update_summary_background(
            conversation_id=conversation_id,
            history=[{"role": "user", "content": "Hello"}],
            previous_summary="Old",
            user_id=user_id,
            session_id=session_id,
        )


# ---------------------------------------------------------------------------
# process_message - save_history=False skips everything
# ---------------------------------------------------------------------------


async def test_process_message_save_history_false_no_conversation_no_history(
    orchestrator, user_id, session_id
):
    """process_message with save_history=False skips conversation and history retrieval entirely."""
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    with patch.object(orchestrator, "_execute_tools", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = []

        orchestrator.client.chat.return_value = {
            "content": "Hello!",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        result = await orchestrator.process_message(
            message="Hello",
            user_id=user_id,
            session_id=session_id,
            save_history=False,
        )

    assert result["intent"] == "no_match"
    assert result["conversation_id"] is None
    orchestrator.chat_service.get_conversation.assert_not_awaited()
    orchestrator.chat_service.create_conversation.assert_not_awaited()
    orchestrator.chat_service.get_conversation_history.assert_not_awaited()


# ---------------------------------------------------------------------------
# process_message_stream - tool path: unknown chunk type (branch 368->364)
# ---------------------------------------------------------------------------


async def test_process_message_stream_tool_path_unknown_chunk_type(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream tool path ignores stream chunks with unknown type."""
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = None

    tool_results = [
        {
            "tool": "search",
            "arguments": {},
            "success": True,
            "data": "found",
            "error": None,
            "save_in_history": True,
        }
    ]

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = tool_results

        async def mock_stream(messages):
            yield {"type": "token", "content": "Hello"}
            yield {"type": "unknown_event", "data": "ignored"}
            yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 5}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Search",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert "done" in event_types
    # The unknown chunk type should not appear in yielded events
    assert "unknown_event" not in event_types


# ---------------------------------------------------------------------------
# process_message_stream - persona path: unknown chunk type + empty content
# ---------------------------------------------------------------------------


async def test_process_message_stream_persona_path_unknown_chunk_type(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream persona path ignores stream chunks with unknown type."""
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = "You are helpful."

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = []

        async def mock_stream(messages):
            yield {"type": "token", "content": "Hello"}
            yield {"type": "unknown_event", "data": "ignored"}
            yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 3}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Who are you?",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert "done" in event_types
    assert "unknown_event" not in event_types


async def test_process_message_stream_persona_path_empty_content(
    orchestrator, user_id, session_id, mock_conversation
):
    """process_message_stream persona path skips save when LLM returns empty content."""
    orchestrator.chat_service.get_or_create_conversation.return_value = (
        mock_conversation,
        False,
    )
    orchestrator.chat_service.get_conversation_history.return_value = []
    orchestrator.prompt_service.get_prompt_for_scopes.return_value = "You are helpful."

    with patch.object(orchestrator, "_try_execute_tools", new_callable=AsyncMock) as mock_try:
        mock_try.return_value = []

        async def mock_stream(messages):
            yield {"type": "usage", "prompt_tokens": 5, "completion_tokens": 0}

        orchestrator.client.stream = mock_stream

        events = []
        async for event in orchestrator.process_message_stream(
            message="Empty question",
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)

    assert events[-1]["type"] == "done"
    # User message saved, but no assistant message (empty content)
    orchestrator.chat_service.add_message.assert_awaited_once_with(
        mock_conversation.id, "user", "Empty question"
    )
