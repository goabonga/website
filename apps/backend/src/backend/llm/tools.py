# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tool definitions and registry for LLM function calling."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from backend.config import settings
from backend.database import async_session_maker
from backend.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    data: Any
    error: str | None = None


@dataclass
class ToolContext:
    """Context passed to tools during execution."""

    user_id: uuid.UUID | str | None = None
    session_id: str | None = None
    conversation_id: uuid.UUID | None = None
    is_authenticated: bool = False
    access_token: str | None = None  # JWT token for auth service calls
    scopes: set[str] | None = None  # User scopes from JWT


@dataclass
class Tool:
    """Tool definition for OpenAI function calling."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[ToolResult]]
    requires_context: bool = False  # If True, handler receives ToolContext as first arg
    hidden: bool = False  # If True, tool is excluded from help_me documentation
    required_scopes: set[str] | None = None  # Scopes required to use this tool (None = public)
    save_in_history: bool = (
        True  # If False, tool interactions are not saved to conversation history
    )


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        requires_context: bool = False,
        hidden: bool = False,
        required_scopes: set[str] | None = None,
        save_in_history: bool = True,
    ) -> Callable[[Callable[..., Awaitable[ToolResult]]], Callable[..., Awaitable[ToolResult]]]:
        """Decorator to register a tool handler.

        Args:
            name: Tool name for OpenAI function calling
            description: Description shown to LLM
            parameters: JSON schema for tool parameters
            requires_context: If True, handler receives ToolContext as first argument
            hidden: If True, tool is excluded from help_me documentation
            required_scopes: Set of scopes required to use this tool (None = public)
            save_in_history: If False, tool interactions are not saved to conversation history
        """

        def decorator(
            func: Callable[..., Awaitable[ToolResult]],
        ) -> Callable[..., Awaitable[ToolResult]]:
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                handler=func,
                requires_context=requires_context,
                hidden=hidden,
                required_scopes=required_scopes,
                save_in_history=save_in_history,
            )
            return func

        return decorator

    def get_tool(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def _is_tool_accessible(self, tool: Tool, user_scopes: set[str] | None) -> bool:
        """Check if a tool is accessible given user scopes.

        Args:
            tool: The tool to check
            user_scopes: User's scopes (None for anonymous users)

        Returns:
            True if tool is accessible
        """
        # Public tools (no required scopes) are always accessible
        if tool.required_scopes is None:
            return True
        # Tools with required scopes need the user to have ALL required scopes
        if user_scopes is None:
            return False
        return tool.required_scopes.issubset(user_scopes)

    def get_openai_tools(self, user_scopes: set[str] | None = None) -> list[dict[str, Any]]:
        """Get tools in OpenAI format, filtered by user scopes.

        Args:
            user_scopes: User's scopes for filtering (None = only public tools)

        Returns:
            List of tools in OpenAI format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
            if self._is_tool_accessible(tool, user_scopes)
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Execute a tool by name with given arguments.

        Args:
            name: Tool name to execute
            arguments: Arguments from LLM function call
            context: Optional context with session/user info
        """
        log_ctx = {
            "user_id": str(context.user_id) if context and context.user_id else None,
            "session_id": context.session_id[:8] if context and context.session_id else None,
            "tool_name": name,
        }

        tool = self._tools.get(name)
        if not tool:
            logger.info("Tool not found: %s", name, extra=log_ctx)
            return ToolResult(
                success=False,
                data=None,
                error=f"Tool '{name}' not found",
            )

        # Check scope requirements
        user_scopes = context.scopes if context else None
        if not self._is_tool_accessible(tool, user_scopes):
            required = ", ".join(tool.required_scopes) if tool.required_scopes else "none"
            logger.info("Tool access denied: %s (requires: %s)", name, required, extra=log_ctx)
            return ToolResult(
                success=False,
                data=None,
                error=f"Access denied: tool '{name}' requires scopes: {required}",
            )

        try:
            logger.info("Executing tool: %s", name, extra=log_ctx)
            if tool.requires_context:
                result = await tool.handler(context or ToolContext(), **arguments)
            else:
                result = await tool.handler(**arguments)

            if result.success:
                logger.info("Tool executed successfully: %s", name, extra=log_ctx)
            else:
                logger.info("Tool execution failed: %s - %s", name, result.error, extra=log_ctx)
            return result
        except Exception as e:
            logger.error("Tool execution error: %s - %s", name, str(e), extra=log_ctx)
            return ToolResult(
                success=False,
                data=None,
                error=str(e),
            )


# Global tool registry
tool_registry = ToolRegistry()


@tool_registry.register(
    name="search_knowledge",
    description="Search the knowledge base for information. Use when the user asks: what do you know about, search for, find information, look up, tell me about, explain, how does X work, what is X, documentation, guide, tutorial, help with understanding.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query - extract the main topic or question from the user's message",
            },
            "namespace": {
                "type": "string",
                "description": "Optional namespace to search in. If not specified, searches all accessible namespaces.",
            },
        },
        "required": ["query"],
    },
    requires_context=True,
)
async def search_knowledge(
    context: ToolContext, query: str, namespace: str | None = None
) -> ToolResult:
    """Search knowledge base using pgvector semantic similarity."""
    from backend.rag.knowledge_base import KnowledgeBase

    async with async_session_maker() as session:
        kb = KnowledgeBase(session)
        results = await kb.search(query, namespace_slug=namespace, user_scopes=context.scopes)

    if not results:
        return ToolResult(
            success=True,
            data={
                "message": "No relevant information found.",
                "query": query,
                "namespace": namespace,
            },
        )

    return ToolResult(
        success=True,
        data={
            "results": [
                {"question": r["question"], "answer": r["answer"], "similarity": r["similarity"]}
                for r in results
            ],
            "query": query,
            "namespace": namespace,
        },
    )


async def _fetch_userinfo(access_token: str) -> dict[str, Any] | None:
    """Fetch user info from auth service.

    Args:
        access_token: JWT access token

    Returns:
        User info dict or None if request fails
    """
    if not settings.oauth2_issuer:
        return None

    userinfo_url = f"{settings.oauth2_issuer.rstrip('/')}/userinfo"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                return response.json()
            return None
    except httpx.RequestError:
        return None


@tool_registry.register(
    name="get_session_info",
    description="Get current user/session information. Use when the user asks: who am I, my profile, my account info, am I logged in, my session, my user ID, my email, what's my name, connection status, authentication status, session details, user details, my photo, my picture, my avatar, profile picture, show my photo.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    requires_context=True,
)
async def get_session_info(context: ToolContext) -> ToolResult:
    """Get current session information, fetching user profile from auth service if authenticated."""
    if context.is_authenticated and context.access_token:
        # Fetch user info from auth service
        userinfo = await _fetch_userinfo(context.access_token)

        if userinfo:
            # Build user-friendly message with available info
            name = userinfo.get("name") or userinfo.get("preferred_username") or "User"
            email = userinfo.get("email")
            email_verified = userinfo.get("email_verified", False)

            message_parts = [f"The user asking the question is authenticated as {name}."]
            if email:
                verified_str = " (verified)" if email_verified else " (not verified)"
                message_parts.append(f"Email: {email}{verified_str}.")
            message_parts.append(f"Conversation ID is {context.conversation_id}.")

            data: dict[str, Any] = {
                "authenticated": True,
                "user_id": str(context.user_id) if context.user_id else None,
                "email": email,
                "email_verified": email_verified,
                "name": userinfo.get("name"),
                "preferred_username": userinfo.get("preferred_username"),
                "picture": userinfo.get("picture"),
                "locale": userinfo.get("locale"),
                "conversation_id": str(context.conversation_id)
                if context.conversation_id
                else None,
                "message": " ".join(message_parts),
            }

            picture = userinfo.get("picture")
            if picture:
                if picture.startswith(("http://", "https://")):
                    picture_url = picture
                else:
                    picture_url = f"{settings.oauth2_issuer.rstrip('/')}/{picture.lstrip('/')}"
                data["picture"] = picture_url
                data["client_action"] = "display_image"
                data["image_url"] = picture_url
                data["image_alt"] = f"Profile picture of {name}"

            return ToolResult(success=True, data=data)
        else:
            # Fallback if userinfo fetch fails
            return ToolResult(
                success=True,
                data={
                    "authenticated": True,
                    "user_id": str(context.user_id) if context.user_id else None,
                    "conversation_id": str(context.conversation_id)
                    if context.conversation_id
                    else None,
                    "message": f"The user is authenticated with user ID {context.user_id}. Conversation ID is {context.conversation_id}.",
                },
            )
    elif context.is_authenticated:
        # Authenticated but no token available
        return ToolResult(
            success=True,
            data={
                "authenticated": True,
                "user_id": str(context.user_id) if context.user_id else None,
                "conversation_id": str(context.conversation_id)
                if context.conversation_id
                else None,
                "message": f"The user is authenticated with user ID {context.user_id}. Conversation ID is {context.conversation_id}.",
            },
        )
    else:
        return ToolResult(
            success=True,
            data={
                "authenticated": False,
                "session_id": context.session_id,
                "conversation_id": str(context.conversation_id)
                if context.conversation_id
                else None,
                "message": f"The user is not authenticated. An anonymous session {context.session_id} has been assigned. Conversation ID is {context.conversation_id}.",
            },
        )


@tool_registry.register(
    name="auth_action",
    description="Trigger authentication actions. Use this when the user mentions: login, log in, logging in, sign in, signing in, connect, authenticate, logout, log out, signing out, disconnect, register, sign up, create account, or access account/profile settings.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["login", "logout", "register", "account"],
                "description": "The authentication action: login (sign in, logging in, connect), logout (sign out, disconnect), register (sign up, create account), account (settings, profile)",
            },
        },
        "required": ["action"],
    },
    requires_context=True,
)
async def auth_action(context: ToolContext, action: str) -> ToolResult:
    """Return client-side action for authentication flows.

    The tool returns an action payload that the client will interpret
    and execute using its auth module (login(), logout() functions).
    """
    if not settings.oauth2_issuer:
        return ToolResult(
            success=False,
            data=None,
            error="Authentication is not configured on this server.",
        )

    # Define available actions - these map to client-side auth.ts functions
    actions = {
        "login": {
            "client_action": "auth_login",
            "message": "I'm initiating the login flow. You'll be redirected to sign in.",
        },
        "logout": {
            "client_action": "auth_logout",
            "message": "I'm logging you out. Your session will be cleared.",
        },
        "register": {
            "client_action": "auth_login",  # Use login flow, auth server handles registration
            "message": "I'm redirecting you to create an account.",
        },
        "account": {
            "client_action": "open_url",
            "url": f"{settings.oauth2_issuer.rstrip('/')}/auth/settings",
            "message": "I'm opening your account settings page.",
        },
    }

    if action not in actions:
        return ToolResult(
            success=False,
            data=None,
            error=f"Unknown action: {action}. Valid actions are: {', '.join(actions.keys())}",
        )

    # Check if action makes sense for current auth state
    if action == "logout" and not context.is_authenticated:
        return ToolResult(
            success=True,
            data={
                "client_action": "none",
                "message": "You are not currently logged in. Would you like to login instead?",
            },
        )

    if action == "login" and context.is_authenticated:
        return ToolResult(
            success=True,
            data={
                "client_action": "none",
                "message": "You are already logged in. Would you like to logout or access your account settings instead?",
            },
        )

    return ToolResult(success=True, data=actions[action])


@tool_registry.register(
    name="new_conversation",
    description="Start a new conversation from scratch. Use when the user wants to: start over, new conversation, reset chat, clear context, fresh start, begin again, start fresh, new topic, change subject completely, forget previous messages.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    requires_context=True,
    save_in_history=False,
)
async def new_conversation(context: ToolContext) -> ToolResult:
    """Archive the current conversation and trigger a new one.

    The current conversation is archived (soft-deleted) but preserved in the database.
    A new conversation will be created on the next message.
    """
    from backend.chat.service import ChatService

    if not context.user_id and not context.session_id:
        return ToolResult(
            success=False,
            data=None,
            error="Cannot start a new conversation without a user or session.",
        )

    async with async_session_maker() as session:
        chat_service = ChatService(session)
        archived = await chat_service.archive_conversation(
            user_id=context.user_id,
            session_id=context.session_id,
        )

        if archived:
            return ToolResult(
                success=True,
                data={
                    "client_action": "new_conversation",
                    "archived_conversation_id": str(archived.id),
                    "message": "I've archived our previous conversation. Starting fresh! How can I help you?",
                },
            )
        else:
            return ToolResult(
                success=True,
                data={
                    "client_action": "new_conversation",
                    "message": "Starting a new conversation. How can I help you?",
                },
            )


# Tool examples for help_me - maps tool name to example prompts
TOOL_EXAMPLES: dict[str, list[str]] = {
    "search_knowledge": [
        "What do you know about Python async programming?",
        "Search for information about Docker containers",
        "Tell me about REST APIs",
        "How does authentication work?",
        "Find documentation on WebSockets",
        "Look up best practices for error handling",
    ],
    "get_session_info": [
        "Who am I?",
        "What's my session ID?",
        "Am I logged in?",
        "Show my profile",
        "What's my email?",
        "My account info",
        "Am I authenticated?",
    ],
    "auth_action": [
        "I want to login",
        "Log in",
        "Logging in",
        "Sign me in",
        "Connect me",
        "Authenticate",
        "Log me out",
        "Sign out",
        "Disconnect",
        "Create an account",
        "Sign up",
        "Register",
        "Account settings",
        "My profile settings",
    ],
    "new_conversation": [
        "Start over",
        "New conversation",
        "Reset chat",
        "Clear context",
        "Fresh start",
        "Begin again",
        "Start fresh",
        "Forget everything",
        "New topic",
    ],
    "help_me": [
        "What can you do?",
        "Help",
        "Help me",
        "Your capabilities",
        "List features",
        "Show commands",
        "How can you help me?",
    ],
}


@tool_registry.register(
    name="help_me",
    description="List available capabilities and features. Use when the user asks: what can you do, help, help me, your capabilities, your features, available commands, what are your functions, how can you help, what do you offer, list features, show me what you can do.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    hidden=True,  # Don't list help_me in its own output
)
async def help_me() -> ToolResult:
    """List all available tools with descriptions and examples."""
    tools_info = []

    for tool in tool_registry._tools.values():
        # Skip tools that are hidden from documentation
        if tool.hidden:
            continue

        tool_data = {
            "name": tool.name,
            "description": tool.description,
            "examples": TOOL_EXAMPLES.get(tool.name, []),
        }
        tools_info.append(tool_data)

    # Build a user-friendly message
    message_parts = ["Here are the available tools and how to use them:\n"]

    for tool_data in tools_info:
        message_parts.append(f"**{tool_data['name']}**")
        message_parts.append(f"  {tool_data['description']}")
        if tool_data["examples"]:
            message_parts.append("  Examples:")
            for example in tool_data["examples"]:
                message_parts.append(f'    - "{example}"')
        message_parts.append("")

    return ToolResult(
        success=True,
        data={
            "tools": tools_info,
            "message": "\n".join(message_parts),
        },
    )
