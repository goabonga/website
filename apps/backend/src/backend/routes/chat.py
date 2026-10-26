# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Chat SSE streaming endpoint."""

from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.orchestrator import ChatOrchestrator
from backend.chat.service import ChatService
from backend.chat.stream import stream_chat_response
from backend.config import settings
from backend.database import get_db
from backend.logging import get_logger
from backend.middleware import check_rate_limit_with_context
from backend.session.cache import ConversationCache
from backend.session.dependencies import ChatContext
from backend.session.service import SessionService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


async def _migrate_anonymous_session(
    db: AsyncSession,
    context: ChatContext,
) -> bool:
    """Migrate anonymous conversation to authenticated user if needed.

    Returns True if migration was performed and cookie should be cleared.
    """
    if not context.is_authenticated or not context.anonymous_session_id or not context.user_id:
        return False

    chat_service = ChatService(db)
    conversation = await chat_service.migrate_conversation(
        context.anonymous_session_id,
        context.user_id,
    )

    if conversation:
        # Invalidate the conversation cache
        cache = ConversationCache(db)
        await cache.invalidate(conversation.id)
        await cache.close()

        # Delete the anonymous session
        session_service = SessionService(db)
        await session_service.delete(context.anonymous_session_id)
        await session_service.close()

        logger.info(
            "Migrated anonymous session %s to user %s",
            context.anonymous_session_id[:8],
            str(context.user_id)[:8],
        )
        return True

    return False


def _clear_session_cookie(response: JSONResponse | StreamingResponse) -> None:
    """Clear the anonymous session cookie."""
    response.delete_cookie(
        key=settings.session_cookie_name,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain or None,
    )


# --- Request Models ---


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., description="The user's message to send to the assistant")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"message": "Hello, how are you?"},
                {"message": "What was my previous question?"},
            ]
        }
    }


# --- SSE Event Models ---


class SSEEventType(StrEnum):
    """Types of SSE events emitted by the chat endpoint."""

    HISTORY = "history"
    INTENT = "intent"
    TOOLS = "tools"
    RAG = "rag"
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"


class IntentType(StrEnum):
    """Intent classification types."""

    TOOL_CALL = "tool_call"
    RAG_SEARCH = "rag_search"
    NO_MATCH = "no_match"


class TokenUsage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = Field(..., description="Number of tokens in the prompt")
    completion_tokens: int = Field(..., description="Number of tokens in the completion")


class MessageItem(BaseModel):
    """A message in conversation history."""

    role: str = Field(..., description="Message role (user or assistant)")
    content: str = Field(..., description="Message content")


class SSEHistoryEvent(BaseModel):
    """SSE event with conversation history."""

    messages: list[MessageItem] = Field(..., description="Previous messages in the conversation")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "messages": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi!"},
                    ]
                }
            ]
        }
    }


class SSEIntentEvent(BaseModel):
    """SSE event for intent classification result."""

    intent: IntentType = Field(..., description="The classified intent of the user message")

    model_config = {"json_schema_extra": {"examples": [{"intent": "rag_search"}]}}


class ToolResult(BaseModel):
    """Result from a tool execution."""

    tool: str = Field(..., description="Name of the executed tool")
    arguments: dict[str, Any] = Field(..., description="Arguments passed to the tool")
    success: bool = Field(..., description="Whether the tool execution succeeded")
    data: Any | None = Field(None, description="Result data if successful")
    error: str | None = Field(None, description="Error message if failed")


class SSEToolsEvent(BaseModel):
    """SSE event for tool execution results."""

    results: list[ToolResult] = Field(..., description="List of tool execution results")


class SSERagEvent(BaseModel):
    """SSE event for RAG search results."""

    count: int = Field(..., description="Number of relevant knowledge base entries found")

    model_config = {"json_schema_extra": {"examples": [{"count": 3}]}}


class SSETokenEvent(BaseModel):
    """SSE event for streaming tokens."""

    content: str = Field(..., description="The token content")

    model_config = {
        "json_schema_extra": {"examples": [{"content": "Hello"}, {"content": " world"}]}
    }


class SSEDoneEvent(BaseModel):
    """SSE event when streaming is complete."""

    usage: TokenUsage = Field(..., description="Token usage statistics for the request")

    model_config = {
        "json_schema_extra": {
            "examples": [{"usage": {"prompt_tokens": 150, "completion_tokens": 50}}]
        }
    }


class SSEErrorEvent(BaseModel):
    """SSE event for errors."""

    message: str = Field(..., description="Error message")

    model_config = {
        "json_schema_extra": {"examples": [{"message": "An error occurred during processing"}]}
    }


# --- Response Models ---


class HistoryResponse(BaseModel):
    """Response model for conversation history (when history=true)."""

    messages: list[MessageItem] = Field(..., description="Conversation messages")
    session_id: str | None = Field(None, description="Session ID (anonymous users only)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "messages": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi! How can I help you?"},
                    ],
                    "session_id": "abc123-def4-5678-90ab-cdef12345678",
                }
            ]
        }
    }


# --- OpenAPI Response Documentation ---


SSE_RESPONSE_DESCRIPTION = """
## Server-Sent Events (SSE) Response

The response is a stream of Server-Sent Events. Each event has a `event` type and `data` payload.

### Event Types

| Event | Description | Data Schema |
|-------|-------------|-------------|
| `history` | Previous conversation messages | `{"messages": [...]}` |
| `intent` | Intent classification result | `{"intent": "tool_call|rag_search|general"}` |
| `tools` | Tool execution results | `{"results": [...]}` |
| `rag` | RAG search result count | `{"count": N}` |
| `token` | Streaming token | `{"content": "..."}` |
| `done` | Stream complete | `{"usage": {...}}` |
| `error` | Error occurred | `{"message": "..."}` |

### Example Stream

```
event: history
data: {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]}

event: intent
data: {"intent": "general"}

event: token
data: {"content": "How"}

event: token
data: {"content": " can"}

event: token
data: {"content": " I help?"}

event: done
data: {"usage": {"prompt_tokens": 150, "completion_tokens": 50}}
```
"""

CHAT_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": SSE_RESPONSE_DESCRIPTION,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["role", "content"],
                            },
                        },
                        "session_id": {"type": "string", "nullable": True},
                    },
                    "required": ["messages"],
                },
                "example": {
                    "messages": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi! How can I help you?"},
                    ],
                    "session_id": "abc123-def4-5678-90ab-cdef12345678",
                },
            },
            "text/event-stream": {
                "schema": {
                    "type": "string",
                    "description": "Server-Sent Events stream",
                },
                "examples": {
                    "history_event": {
                        "summary": "Conversation history event",
                        "value": 'event: history\ndata: {"messages": []}\n\n',
                    },
                    "intent_event": {
                        "summary": "Intent classification event",
                        "value": 'event: intent\ndata: {"intent": "general"}\n\n',
                    },
                    "token_event": {
                        "summary": "Token streaming event",
                        "value": 'event: token\ndata: {"content": "Hello"}\n\n',
                    },
                    "done_event": {
                        "summary": "Completion event",
                        "value": 'event: done\ndata: {"usage": {"prompt_tokens": 150, "completion_tokens": 50}}\n\n',
                    },
                },
            },
        },
    },
    429: {"description": "Rate limit exceeded"},
}


@router.post(
    "",
    response_model=None,
    responses=CHAT_RESPONSES,
    summary="Chat or get conversation history",
    description="""Send a message and receive a streaming response via SSE, or get conversation history.

**Query Parameters:**
- `history=true` - Return conversation history as JSON (no message processing)
- `history=false` (default) - Process message and stream response via SSE
""",
)
async def chat(
    request: ChatRequest,
    history: bool = Query(
        False,
        description="If true, return conversation history as JSON instead of processing the message",
    ),
    db: AsyncSession = Depends(get_db),
    context: ChatContext = Depends(check_rate_limit_with_context),
):
    """
    Chat endpoint with dual response modes.

    **Modes:**
    - `?history=true` - Returns conversation history as JSON (ignores message body)
    - `?history=false` (default) - Processes message and streams response via SSE

    **Authentication:**
    - `Authorization: Bearer <token>` - For authenticated users (JWT)
    - Cookie `session_id` - For anonymous users (httpOnly, automatic)

    **SSE Response Events:**
    - `history` - Previous conversation messages (always first)
    - `intent` - Intent classification result
    - `tools` - Tool execution results (if intent is tool_call)
    - `rag` - RAG search result count (if intent is rag_search)
    - `token` - Streaming response tokens
    - `done` - Stream completion with usage stats
    - `error` - Error information if something went wrong
    """
    user_type = "authenticated" if context.is_authenticated else "anonymous"

    # Migrate anonymous session to authenticated user if needed
    session_migrated = await _migrate_anonymous_session(db, context)

    # History mode: return conversation history as JSON
    if history:
        logger.info(
            "History request received",
            extra={
                "user_id": str(context.user_id) if context.user_id else None,
                "session_id": context.session_id[:8] if context.session_id else None,
                "user_type": user_type,
            },
        )

        chat_service = ChatService(db)
        conversation, _ = await chat_service.get_or_create_conversation(
            user_id=context.user_id,
            session_id=context.session_id,
        )
        messages = await chat_service.get_conversation_history(conversation.id)

        response: JSONResponse | StreamingResponse = JSONResponse(
            content=HistoryResponse(
                messages=[MessageItem(role=m["role"], content=m["content"]) for m in messages],
                session_id=context.session_id if not context.is_authenticated else None,
            ).model_dump()
        )

        # Set httpOnly cookie for new sessions
        if context.session_created and context.session_id:
            response.set_cookie(
                key=settings.session_cookie_name,
                value=context.session_id,
                max_age=settings.session_cookie_max_age,
                httponly=True,
                secure=settings.session_cookie_secure,
                samesite=settings.session_cookie_samesite,
                domain=settings.session_cookie_domain or None,
            )

        # Clear session cookie after migration
        if session_migrated:
            _clear_session_cookie(response)

        return response

    # Chat mode: process message and stream response
    logger.info(
        "Chat request received",
        extra={
            "user_id": str(context.user_id) if context.user_id else None,
            "session_id": context.session_id[:8] if context.session_id else None,
            "user_type": user_type,
            "message_length": len(request.message),
        },
    )
    logger.debug(
        "Chat message content: %s",
        request.message[:100] + "..." if len(request.message) > 100 else request.message,
    )

    orchestrator = ChatOrchestrator(db)

    async def generate():
        try:
            async for chunk in stream_chat_response(
                orchestrator.process_message_stream(
                    message=request.message,
                    user_id=context.user_id,
                    session_id=context.session_id,
                    access_token=context.access_token,
                    user_scopes=context.scopes,
                )
            ):
                yield chunk
        except Exception as e:
            logger.error("Error during chat streaming: %s", str(e), exc_info=True)
            raise

    logger.debug(
        "Starting SSE stream for %s %s",
        user_type,
        str(context.user_id)[:8]
        if context.user_id
        else (context.session_id[:8] if context.session_id else "unknown"),
    )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    response = StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=headers,
    )

    # Set httpOnly cookie for new sessions
    if context.session_created and context.session_id:
        response.set_cookie(
            key=settings.session_cookie_name,
            value=context.session_id,
            max_age=settings.session_cookie_max_age,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite,
            domain=settings.session_cookie_domain or None,
        )
        logger.debug("Set session cookie for session: %s", context.session_id[:8])

    # Clear session cookie after migration
    if session_migrated:
        _clear_session_cookie(response)

    return response
