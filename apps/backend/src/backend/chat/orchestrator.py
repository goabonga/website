# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Chat orchestrator for multi-step LLM processing."""

import asyncio
import copy
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.service import ChatService
from backend.database import async_session_maker
from backend.llm.client import OpenAIClient
from backend.llm.tools import ToolContext, ToolResult, tool_registry
from backend.logging import get_logger
from backend.prompts.service import PromptService
from backend.rag.knowledge_base import KnowledgeBase

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a helpful AI assistant. You provide accurate, helpful, and concise responses.

When responding:
- Be direct and helpful
- If you used information from the knowledge base, integrate it naturally
- If you don't know something, say so honestly
- Keep responses focused and relevant
"""

TOOL_SYSTEM_PROMPT = """You are a helpful AI assistant with access to tools.

IMPORTANT RULES:
1. You can call multiple tools in a single request if needed
2. Call all relevant tools that help answer the user's question
3. If tools are independent, call them in parallel for efficiency
4. When the user asks about THEMSELVES ("who am I", "qui suis-je", "my profile", "my account"), call get_session_info
5. When the user asks about YOU ("who are you", "qui es-tu", "what's your name", "when were you born", "your job"), do NOT call get_session_info - these are questions about the assistant persona, not the user

The tools are provided via function calling. Analyze the user's message and call all appropriate tools.
"""

TOOL_CONTEXT_TEMPLATE = """The following are results from tool calls - treat them as factual data:

{context}

IMPORTANT: If tool results contain user profile or session information (from get_session_info),
that data describes THE USER who is asking the question - not you, the assistant.
Even if you have a persona or character, present tool-returned user data as the USER's profile,
never as your own identity. Answer in the user's language."""

TITLE_GENERATION_PROMPT = """Generate a very short title (max 5 words) summarizing this conversation.
Return ONLY the title, no quotes, no explanation.

Conversation:
{conversation}"""

SUMMARY_GENERATION_PROMPT = """Summarize this conversation concisely, capturing key topics, decisions, and context.
Keep it brief (2-4 sentences max) but include important details the assistant should remember.

{previous_summary}

Recent messages:
{recent_messages}

Return ONLY the summary, no explanation."""

SUMMARY_CONTEXT_TEMPLATE = """Previous conversation summary:
{summary}

Use this context to maintain continuity in the conversation."""


# Generate title on first message and every N messages
TITLE_UPDATE_INTERVAL = 5
# Update summary every N user messages
SUMMARY_UPDATE_INTERVAL = 3


class ChatOrchestrator:
    """Orchestrates multi-step LLM processing with tools and RAG."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.client = OpenAIClient()
        self.chat_service = ChatService(session)
        self.knowledge_base = KnowledgeBase(session)
        self.prompt_service = PromptService(session)

    def _log_context(self, user_id: uuid.UUID | str | None, session_id: str | None) -> dict:
        """Build logging context with user/session info."""
        return {
            "user_id": str(user_id) if user_id else None,
            "session_id": session_id[:8] if session_id else None,
        }

    async def process_message(
        self,
        message: str,
        conversation_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
        save_history: bool = True,
        user_scopes: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        Process a user message through the orchestration pipeline.

        Flow:
        1. Try to execute tools (if applicable)
        2. If no tool executed, return fallback message

        Args:
            message: The user's message
            conversation_id: Optional conversation ID for history
            user_id: Optional user ID for authenticated users
            session_id: Optional session ID for anonymous users
            save_history: Whether to save messages to database
            user_scopes: Optional user scopes for filtering tools and namespaces

        Returns:
            Dict with response content and metadata
        """
        log_ctx = self._log_context(user_id, session_id)
        logger.info("Processing message (non-streaming)", extra=log_ctx)
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        # Create or get conversation
        conversation = None
        conversation_summary = None
        if save_history:
            if conversation_id:
                conversation = await self.chat_service.get_conversation(
                    conversation_id, user_id, session_id
                )
                if not conversation:
                    conversation = await self.chat_service.create_conversation(user_id, session_id)
            else:
                conversation = await self.chat_service.create_conversation(user_id, session_id)
            conversation_id = conversation.id
            conversation_summary = conversation.summary

        # Get conversation history
        history = []
        if conversation_id and save_history:
            history = await self.chat_service.get_conversation_history(conversation_id, limit=20)

        # Load system prompt based on user scopes
        system_prompt = await self.prompt_service.get_prompt_for_scopes(user_scopes)

        # Step 1: Try to execute tools first (priority)
        tool_context = ToolContext(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            is_authenticated=user_id is not None,
            scopes=user_scopes,
        )
        tool_results = await self._execute_tools(message, history, tool_context)

        if tool_results:
            # Tool was executed - generate response with tool context
            logger.info("Executed %d tools", len(tool_results), extra=log_ctx)
            context = self._format_tool_results(tool_results)

            response = await self._generate_response(
                message=message,
                history=history,
                context=context,
                summary=conversation_summary,
                system_prompt=system_prompt,
            )

            total_usage["prompt_tokens"] += response.get("usage", {}).get("prompt_tokens", 0)
            total_usage["completion_tokens"] += response.get("usage", {}).get(
                "completion_tokens", 0
            )

            return {
                "content": response.get("content", ""),
                "conversation_id": str(conversation_id) if conversation_id else None,
                "intent": "tool_call",
                "usage": total_usage,
                "tool_results": tool_results,
            }

        # Step 2: No tool executed - generate response with persona prompt
        logger.info("No tool executed, generating persona response", extra=log_ctx)

        response = await self._generate_response(
            message=message,
            history=history,
            context="",
            summary=conversation_summary,
            system_prompt=system_prompt,
        )

        total_usage["prompt_tokens"] += response.get("usage", {}).get("prompt_tokens", 0)
        total_usage["completion_tokens"] += response.get("usage", {}).get("completion_tokens", 0)

        return {
            "content": response.get("content", ""),
            "conversation_id": str(conversation_id) if conversation_id else None,
            "intent": "no_match",
            "usage": total_usage,
            "tool_results": None,
        }

    async def process_message_stream(
        self,
        message: str,
        user_id: uuid.UUID | str | None = None,
        session_id: str | None = None,
        access_token: str | None = None,
        user_scopes: set[str] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Process a user message with streaming response.

        Flow:
        1. Try to execute tools (if applicable)
        2. If no tool executed, return fallback message

        Args:
            message: The user's message
            user_id: Optional user ID for authenticated users
            session_id: Optional session ID for anonymous users
            access_token: Optional JWT token for auth service calls
            user_scopes: Optional user scopes from JWT (for tool/namespace filtering)

        Yields:
            Events: history, intent, tools/rag, tokens, done
        """
        log_ctx = self._log_context(user_id, session_id)
        logger.info("Processing message (streaming)", extra=log_ctx)
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        # Get or create the unique conversation for this user/session
        conversation, _ = await self.chat_service.get_or_create_conversation(user_id, session_id)
        conversation_id = conversation.id
        conversation_summary = conversation.summary

        # Get existing history (before adding new message)
        history = await self.chat_service.get_conversation_history(conversation_id, limit=20)

        # Yield history as first event
        yield {"type": "history", "messages": history}

        # Load system prompt based on user scopes
        system_prompt = await self.prompt_service.get_prompt_for_scopes(user_scopes)

        # Step 1: Try to execute tools first (priority)
        tool_context = ToolContext(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            is_authenticated=user_id is not None,
            access_token=access_token,
            scopes=user_scopes,
        )

        tool_results = await self._try_execute_tools(message, history, tool_context)

        if tool_results:
            # Tool was executed - check if any tool wants to save to history
            should_save_history = any(r.get("save_in_history", True) for r in tool_results)
            logger.info(
                "Stream: executed %d tools, save_in_history=%s",
                len(tool_results),
                should_save_history,
                extra=log_ctx,
            )
            yield {"type": "intent", "intent": "tool_call"}
            yield {"type": "tools", "results": tool_results}

            # Save user message to history (if any tool allows it)
            if should_save_history:
                await self.chat_service.add_message(conversation_id, "user", message)

            context = self._format_tool_results(tool_results)

            # Stream response with tool context
            messages = self._build_messages(
                message, history, context, conversation_summary, system_prompt
            )
            full_content = ""

            async for chunk in self.client.stream(messages):
                if chunk["type"] == "token":
                    full_content += chunk["content"]
                    yield {"type": "token", "content": chunk["content"]}
                elif chunk["type"] == "usage":
                    total_usage["prompt_tokens"] += chunk.get("prompt_tokens", 0)
                    total_usage["completion_tokens"] += chunk.get("completion_tokens", 0)

            # Save assistant response and update title/summary (if any tool allows it)
            if full_content and should_save_history:
                await self.chat_service.add_message(conversation_id, "assistant", full_content)

                updated_history = history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": full_content},
                ]
                message_count = len(updated_history)

                if self._should_update_title(message_count):
                    asyncio.create_task(
                        self._update_title_background(
                            conversation_id, updated_history, user_id, session_id
                        )
                    )

                if self._should_update_summary(message_count):
                    asyncio.create_task(
                        self._update_summary_background(
                            conversation_id,
                            updated_history,
                            conversation_summary,
                            user_id,
                            session_id,
                        )
                    )

            logger.info(
                "Stream completed (tool): %d prompt tokens, %d completion tokens",
                total_usage["prompt_tokens"],
                total_usage["completion_tokens"],
                extra=log_ctx,
            )
            yield {
                "type": "done",
                "conversation_id": str(conversation_id) if conversation_id else None,
                "usage": total_usage,
            }
            return

        # Step 2: No tool executed - generate response with persona prompt
        yield {"type": "intent", "intent": "no_match"}

        # Save user message to history
        await self.chat_service.add_message(conversation_id, "user", message)

        logger.info("Stream: no tool executed, generating persona response", extra=log_ctx)

        # Stream response with persona prompt
        messages = self._build_messages(message, history, "", conversation_summary, system_prompt)
        full_content = ""

        async for chunk in self.client.stream(messages):
            if chunk["type"] == "token":
                full_content += chunk["content"]
                yield {"type": "token", "content": chunk["content"]}
            elif chunk["type"] == "usage":
                total_usage["prompt_tokens"] += chunk.get("prompt_tokens", 0)
                total_usage["completion_tokens"] += chunk.get("completion_tokens", 0)

        # Save assistant response and update title/summary
        if full_content:
            await self.chat_service.add_message(conversation_id, "assistant", full_content)

            updated_history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": full_content},
            ]
            message_count = len(updated_history)

            if self._should_update_title(message_count):
                asyncio.create_task(
                    self._update_title_background(
                        conversation_id, updated_history, user_id, session_id
                    )
                )

            if self._should_update_summary(message_count):
                asyncio.create_task(
                    self._update_summary_background(
                        conversation_id,
                        updated_history,
                        conversation_summary,
                        user_id,
                        session_id,
                    )
                )

        logger.info(
            "Stream completed (persona): %d prompt tokens, %d completion tokens",
            total_usage["prompt_tokens"],
            total_usage["completion_tokens"],
            extra=log_ctx,
        )
        yield {
            "type": "done",
            "conversation_id": str(conversation_id) if conversation_id else None,
            "usage": total_usage,
        }

    async def _enhance_tools_with_namespaces(
        self,
        tools: list[dict[str, Any]],
        user_scopes: set[str] | None,
    ) -> list[dict[str, Any]]:
        """Inject accessible namespace info into the search_knowledge tool definition.

        Fetches namespaces from the database, adds an enum constraint and
        descriptions to the namespace parameter so the LLM can target specific namespaces.
        """
        namespaces = await self.knowledge_base.list_namespaces(user_scopes)
        if not namespaces:
            return tools

        search_tool = None
        for tool in tools:
            if tool.get("function", {}).get("name") == "search_knowledge":
                search_tool = tool
                break

        if search_tool is None:
            return tools

        ns_param = (
            search_tool["function"].get("parameters", {}).get("properties", {}).get("namespace")
        )
        if ns_param is None:
            return tools

        # Deepcopy to avoid mutating the global registry's Tool.parameters
        search_tool["function"] = copy.deepcopy(search_tool["function"])

        slugs = [ns.slug for ns in namespaces]
        namespace_lines = [
            f"- {ns.slug}: {ns.name}" + (f" ({ns.description})" if ns.description else "")
            for ns in namespaces
        ]

        search_tool["function"]["parameters"]["properties"]["namespace"] = {
            "type": "string",
            "description": (
                "Optional namespace to restrict the search. Available namespaces:\n"
                + "\n".join(namespace_lines)
            ),
            "enum": slugs,
        }

        return tools

    async def _try_execute_tools(
        self,
        message: str,
        history: list[dict],
        tool_context: ToolContext,
    ) -> list[dict]:
        """Try to execute tools for the message.

        Uses the LLM with tool_choice="auto" to determine if any tools should be called.
        Returns empty list if no tools are applicable.

        Args:
            message: User message
            history: Conversation history
            tool_context: Context with user/session info for tools that need it

        Returns:
            List of tool results, or empty list if no tools were executed
        """
        # Get tools filtered by user scopes, enhanced with namespace info
        tools = tool_registry.get_openai_tools(tool_context.scopes)
        tools = await self._enhance_tools_with_namespaces(tools, tool_context.scopes)

        if not tools:
            return []

        # Build messages with tool-specific system prompt
        messages: list[ChatCompletionMessageParam] = cast(
            list[ChatCompletionMessageParam],
            [{"role": "system", "content": TOOL_SYSTEM_PROMPT}],
        )
        messages.extend(cast(list[ChatCompletionMessageParam], history))
        messages.append(cast(ChatCompletionMessageParam, {"role": "user", "content": message}))

        # Let the LLM decide which tool to call based on the message
        response = await self.client.chat(messages, tools=tools, tool_choice="auto")
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            return []

        log_ctx = self._log_context(
            tool_context.user_id if tool_context else None,
            tool_context.session_id if tool_context else None,
        )
        logger.info("Executing %d tool call(s)", len(tool_calls), extra=log_ctx)

        results = []
        for tool_call in tool_calls:
            name = tool_call["name"]
            arguments = tool_call["arguments"]

            logger.info("Executing tool: %s", name, extra=log_ctx)
            logger.debug("Tool %s arguments: %s", name, arguments, extra=log_ctx)
            result: ToolResult = await tool_registry.execute(name, arguments, tool_context)
            if result.success:
                logger.info("Tool %s succeeded", name, extra=log_ctx)
            else:
                logger.error("Tool %s failed: %s", name, result.error, extra=log_ctx)

            # Get save_in_history from tool definition
            tool = tool_registry.get_tool(name)
            save_in_history = tool.save_in_history if tool else True

            results.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                    "save_in_history": save_in_history,
                }
            )

        return results

    async def _execute_tools(
        self,
        message: str,
        history: list[dict],
        tool_context: ToolContext | None = None,
    ) -> list[dict]:
        """Execute tool calls based on the message (legacy method for non-streaming).

        Args:
            message: User message
            history: Conversation history
            tool_context: Context with user/session info for tools that need it
        """
        # Build messages with tool-specific system prompt
        messages: list[ChatCompletionMessageParam] = cast(
            list[ChatCompletionMessageParam],
            [{"role": "system", "content": TOOL_SYSTEM_PROMPT}],
        )
        messages.extend(cast(list[ChatCompletionMessageParam], history))
        messages.append(cast(ChatCompletionMessageParam, {"role": "user", "content": message}))

        # Get tools filtered by user scopes, enhanced with namespace info
        user_scopes = tool_context.scopes if tool_context else None
        tools = tool_registry.get_openai_tools(user_scopes)
        tools = await self._enhance_tools_with_namespaces(tools, user_scopes)

        if not tools:
            return []

        # Let the LLM decide which tool to call based on the message
        response = await self.client.chat(messages, tools=tools, tool_choice="auto")
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            return []

        log_ctx = self._log_context(
            tool_context.user_id if tool_context else None,
            tool_context.session_id if tool_context else None,
        )
        logger.info("Executing %d tool call(s) (legacy)", len(tool_calls), extra=log_ctx)

        results = []
        for tool_call in tool_calls:
            name = tool_call["name"]
            arguments = tool_call["arguments"]

            logger.info("Executing tool: %s", name, extra=log_ctx)
            logger.debug("Tool %s arguments: %s", name, arguments, extra=log_ctx)
            result: ToolResult = await tool_registry.execute(name, arguments, tool_context)
            if result.success:
                logger.info("Tool %s succeeded", name, extra=log_ctx)
            else:
                logger.error("Tool %s failed: %s", name, result.error, extra=log_ctx)

            # Get save_in_history from tool definition
            tool = tool_registry.get_tool(name)
            save_in_history = tool.save_in_history if tool else True

            results.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                    "save_in_history": save_in_history,
                }
            )

        return results

    async def _generate_response(
        self,
        message: str,
        history: list[dict],
        context: str,
        summary: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Generate the final response.

        Args:
            message: The user's message
            history: Conversation history
            context: RAG or tool context
            summary: Optional conversation summary
            system_prompt: Custom system prompt (falls back to default)
        """
        messages = self._build_messages(message, history, context, summary, system_prompt)
        return await self.client.chat(messages)

    def _build_messages(
        self,
        message: str,
        history: list[dict],
        context: str,
        summary: str | None = None,
        system_prompt: str | None = None,
    ) -> list[ChatCompletionMessageParam]:
        """Build the messages list for the LLM.

        Args:
            message: The user's message
            history: Conversation history
            context: RAG or tool context to include
            summary: Optional conversation summary
            system_prompt: Custom system prompt (falls back to SYSTEM_PROMPT constant)
        """
        prompt_content = system_prompt or SYSTEM_PROMPT
        messages = [{"role": "system", "content": prompt_content}]

        # Add conversation summary if available
        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": SUMMARY_CONTEXT_TEMPLATE.format(summary=summary),
                }
            )

        if context:
            messages.append(
                {
                    "role": "system",
                    "content": TOOL_CONTEXT_TEMPLATE.format(context=context),
                }
            )

        messages.extend(history)
        messages.append({"role": "user", "content": message})

        return cast(list[ChatCompletionMessageParam], messages)

    def _format_tool_results(self, results: list[dict]) -> str:
        """Format tool results as context."""
        formatted = []
        for result in results:
            if result["success"]:
                formatted.append(f"Tool '{result['tool']}' returned: {result['data']}")
            else:
                formatted.append(f"Tool '{result['tool']}' failed: {result['error']}")
        return "\n".join(formatted)

    async def _generate_title(self, history: list[dict]) -> str:
        """Generate a short title for a conversation based on its history."""
        # Format conversation history for title generation
        conversation_text = "\n".join(
            f"{msg['role'].capitalize()}: {msg['content'][:100]}"
            for msg in history[-10:]  # Use last 10 messages max
        )
        prompt = TITLE_GENERATION_PROMPT.format(conversation=conversation_text[:500])
        messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.client.chat(messages)
            title = response.get("content", "").strip()
            # Limit title length and clean up
            title = title[:100].strip("\"'")
            if not title:
                title = "New conversation"
            logger.debug("Generated title: %s", title)
            return title
        except Exception as e:
            logger.warning("Failed to generate title: %s", e)
            return "New conversation"

    def _should_update_title(self, message_count: int) -> bool:
        """Check if title should be updated based on message count.

        Updates on first exchange (2 messages) and every TITLE_UPDATE_INTERVAL user messages.

        Args:
            message_count: Total message count (user + assistant messages)
        """
        # message_count includes both user and assistant messages
        # First exchange = 2 messages (1 user + 1 assistant)
        if message_count <= 2:
            return True
        # We want to update every 5 user messages, so every 10 total messages
        user_message_count = message_count // 2
        return user_message_count % TITLE_UPDATE_INTERVAL == 0

    async def _update_title_background(
        self,
        conversation_id: uuid.UUID,
        history: list[dict],
        user_id: uuid.UUID | str | None,
        session_id: str | None,
    ) -> None:
        """Update conversation title in background.

        Creates its own database session since this runs after the request session is closed.
        """
        try:
            title = await self._generate_title(history)
            # Create a new session for background task
            async with async_session_maker() as session:
                chat_service = ChatService(session)
                await chat_service.update_title(conversation_id, title, user_id, session_id)
            logger.info("Updated title for conversation %s: %s", conversation_id, title)
        except Exception as e:
            logger.warning("Failed to update title in background: %s", e)

    async def _generate_summary(
        self,
        history: list[dict],
        previous_summary: str | None = None,
    ) -> str:
        """Generate a summary of the conversation."""
        # Format recent messages
        recent_messages = "\n".join(
            f"{msg['role'].capitalize()}: {msg['content'][:200]}"
            for msg in history[-6:]  # Last 3 exchanges
        )

        previous_summary_text = (
            f"Previous summary:\n{previous_summary}" if previous_summary else "No previous summary."
        )

        prompt = SUMMARY_GENERATION_PROMPT.format(
            previous_summary=previous_summary_text,
            recent_messages=recent_messages,
        )
        messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.client.chat(messages)
            summary = response.get("content", "").strip()
            if not summary:
                return previous_summary or ""
            logger.debug("Generated summary: %s", summary[:100])
            return summary
        except Exception as e:
            logger.warning("Failed to generate summary: %s", e)
            return previous_summary or ""

    def _should_update_summary(self, message_count: int) -> bool:
        """Check if summary should be updated based on message count.

        Updates every SUMMARY_UPDATE_INTERVAL user messages (starting after first).
        """
        if message_count < 4:  # Need at least 2 exchanges before summarizing
            return False
        user_message_count = (message_count + 1) // 2
        return user_message_count % SUMMARY_UPDATE_INTERVAL == 0

    async def _update_summary_background(
        self,
        conversation_id: uuid.UUID,
        history: list[dict],
        previous_summary: str | None,
        user_id: uuid.UUID | str | None,
        session_id: str | None,
    ) -> None:
        """Update conversation summary in background.

        Creates its own database session since this runs after the request session is closed.
        """
        try:
            summary = await self._generate_summary(history, previous_summary)
            # Create a new session for background task
            async with async_session_maker() as session:
                chat_service = ChatService(session)
                await chat_service.update_summary(conversation_id, summary, user_id, session_id)
            logger.info("Updated summary for conversation %s", conversation_id)
        except Exception as e:
            logger.warning("Failed to update summary in background: %s", e)
