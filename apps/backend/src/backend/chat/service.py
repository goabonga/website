# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Chat service for conversation management."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.logging import get_logger
from backend.models.conversation import Conversation, Message

logger = get_logger(__name__)


class ChatService:
    """Service for managing conversations and messages."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_conversation(
        self,
        user_id: uuid.UUID | str | None = None,
        session_id: str | None = None,
        title: str | None = None,
    ) -> Conversation:
        """Create a new conversation.

        Args:
            user_id: Optional user ID (for authenticated users)
            session_id: Optional session ID (for anonymous users)
            title: Optional conversation title
        """
        conversation = Conversation(
            user_id=user_id,
            session_id=session_id,
            title=title,
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)

        logger.info(
            "Created conversation: %s",
            conversation.id,
            extra={
                "user_id": str(user_id) if user_id else None,
                "session_id": session_id[:8] if session_id else None,
            },
        )
        return conversation

    async def get_or_create_conversation(
        self,
        user_id: uuid.UUID | str | None = None,
        session_id: str | None = None,
    ) -> tuple[Conversation, bool]:
        """Get the unique active conversation for a user/session, or create one.

        Each user or session has exactly one active (non-archived) conversation.

        Args:
            user_id: Optional user ID (for authenticated users)
            session_id: Optional session ID (for anonymous users)

        Returns:
            Tuple of (conversation, created) where created is True if new
        """
        stmt = select(Conversation).options(selectinload(Conversation.messages))
        # Exclude archived conversations
        stmt = stmt.where(Conversation.archived_at.is_(None))

        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        elif session_id is not None:
            stmt = stmt.where(Conversation.session_id == session_id)
        else:
            # No owner - create a new ephemeral conversation
            new_conversation = await self.create_conversation()
            return new_conversation, True

        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if conversation:
            logger.info(
                "Found existing conversation %s",
                conversation.id,
                extra={
                    "user_id": str(user_id) if user_id else None,
                    "session_id": session_id[:8] if session_id else None,
                },
            )
            return conversation, False

        # Create new conversation
        conversation = await self.create_conversation(user_id, session_id)
        return conversation, True

    async def get_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | str | None = None,
        session_id: str | None = None,
    ) -> Conversation | None:
        """Get a conversation by ID with its messages.

        Args:
            conversation_id: The conversation UUID
            user_id: Optional user ID filter (for authenticated users)
            session_id: Optional session ID filter (for anonymous users)
        """
        logger.debug("Fetching conversation: %s", conversation_id)
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )

        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        elif session_id is not None:
            stmt = stmt.where(Conversation.session_id == session_id)

        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()
        if conversation:
            logger.debug(
                "Found conversation %s with %d messages",
                conversation_id,
                len(conversation.messages),
            )
        else:
            logger.debug("Conversation %s not found", conversation_id)
        return conversation

    async def list_conversations(
        self,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for a user or session.

        Args:
            user_id: Optional user ID filter (for authenticated users)
            session_id: Optional session ID filter (for anonymous users)
            limit: Maximum number of results
            offset: Number of results to skip
        """
        stmt = select(Conversation).order_by(Conversation.updated_at.desc())

        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        elif session_id is not None:
            stmt = stmt.where(Conversation.session_id == session_id)
        else:
            return []

        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
    ) -> Message:
        """Add a message to a conversation."""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        logger.debug("Added %s message to conversation %s", role, conversation_id)
        return message

    async def get_conversation_history(
        self,
        conversation_id: uuid.UUID,
        limit: int | None = None,
    ) -> list[dict]:
        """Get conversation history as a list of message dicts."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        messages = result.scalars().all()

        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def update_title(
        self,
        conversation_id: uuid.UUID,
        title: str,
        user_id: uuid.UUID | str | None = None,
        session_id: str | None = None,
    ) -> Conversation | None:
        """Update conversation title.

        Args:
            conversation_id: The conversation UUID
            title: New title
            user_id: Optional user ID filter (for authenticated users)
            session_id: Optional session ID filter (for anonymous users)
        """
        conversation = await self.get_conversation(conversation_id, user_id, session_id)
        if not conversation:
            return None

        conversation.title = title
        await self.session.commit()
        await self.session.refresh(conversation)

        logger.info("Updated title for conversation %s", conversation_id)
        return conversation

    async def update_summary(
        self,
        conversation_id: uuid.UUID,
        summary: str,
        user_id: uuid.UUID | str | None = None,
        session_id: str | None = None,
    ) -> Conversation | None:
        """Update conversation summary.

        Args:
            conversation_id: The conversation UUID
            summary: New summary
            user_id: Optional user ID filter (for authenticated users)
            session_id: Optional session ID filter (for anonymous users)
        """
        conversation = await self.get_conversation(conversation_id, user_id, session_id)
        if not conversation:
            return None

        conversation.summary = summary
        await self.session.commit()
        await self.session.refresh(conversation)

        logger.debug("Updated summary for conversation %s", conversation_id)
        return conversation

    async def delete_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
    ) -> bool:
        """Delete a conversation and its messages.

        Args:
            conversation_id: The conversation UUID
            user_id: Optional user ID filter (for authenticated users)
            session_id: Optional session ID filter (for anonymous users)
        """
        conversation = await self.get_conversation(conversation_id, user_id, session_id)
        if not conversation:
            return False

        await self.session.delete(conversation)
        await self.session.commit()

        logger.info(
            "Deleted conversation: %s",
            conversation_id,
            extra={
                "user_id": str(user_id) if user_id else None,
                "session_id": session_id[:8] if session_id else None,
            },
        )
        return True

    async def reset_conversation(
        self,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
    ) -> bool:
        """Delete the conversation for a user/session.

        Used to reset and start fresh.

        Args:
            user_id: Optional user ID (for authenticated users)
            session_id: Optional session ID (for anonymous users)

        Returns:
            True if a conversation was deleted, False if none existed
        """
        stmt = select(Conversation)

        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        elif session_id is not None:
            stmt = stmt.where(Conversation.session_id == session_id)
        else:
            return False

        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            return False

        await self.session.delete(conversation)
        await self.session.commit()

        logger.info(
            "Reset conversation",
            extra={
                "user_id": str(user_id) if user_id else None,
                "session_id": session_id[:8] if session_id else None,
            },
        )
        return True

    async def archive_conversation(
        self,
        user_id: uuid.UUID | str | None = None,
        session_id: str | None = None,
    ) -> Conversation | None:
        """Archive the current conversation for a user/session.

        The conversation is soft-archived by setting archived_at timestamp.
        Messages are preserved but the conversation is excluded from active queries.

        Args:
            user_id: Optional user ID (for authenticated users)
            session_id: Optional session ID (for anonymous users)

        Returns:
            The archived conversation, or None if no active conversation exists
        """
        stmt = select(Conversation).where(Conversation.archived_at.is_(None))

        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        elif session_id is not None:
            stmt = stmt.where(Conversation.session_id == session_id)
        else:
            return None

        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            return None

        conversation.archived_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(conversation)

        logger.info(
            "Archived conversation %s",
            conversation.id,
            extra={
                "user_id": str(user_id) if user_id else None,
                "session_id": session_id[:8] if session_id else None,
            },
        )
        return conversation

    async def migrate_conversation(
        self,
        session_id: str,
        user_id: uuid.UUID | str,
    ) -> Conversation | None:
        """Migrate an anonymous conversation to an authenticated user.

        Transfers ownership of the conversation from the anonymous session
        to the authenticated user. If the user already has a conversation,
        the anonymous conversation messages are merged into it.

        Args:
            session_id: The anonymous session ID
            user_id: The authenticated user's ID

        Returns:
            The migrated/merged conversation, or None if no anonymous conversation
        """
        # Find anonymous conversation
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.session_id == session_id)
            .where(Conversation.user_id.is_(None))
        )
        result = await self.session.execute(stmt)
        anon_conversation = result.scalar_one_or_none()

        if not anon_conversation:
            logger.info(
                "No anonymous conversation to migrate",
                extra={"user_id": str(user_id), "session_id": session_id[:8]},
            )
            return None

        # Check if user already has a conversation
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        user_conversation = result.scalar_one_or_none()

        if user_conversation:
            # User already has a conversation - merge messages
            logger.info(
                "Merging anonymous conversation %s into user conversation %s",
                str(anon_conversation.id)[:8],
                str(user_conversation.id)[:8],
                extra={"user_id": str(user_id), "session_id": session_id[:8]},
            )

            # Move messages from anonymous to user conversation
            for msg in anon_conversation.messages:
                msg.conversation_id = user_conversation.id

            # Delete the anonymous conversation (messages already moved)
            anon_conversation.messages = []
            await self.session.delete(anon_conversation)
            await self.session.commit()
            await self.session.refresh(user_conversation)

            logger.info(
                "Merged %d messages from anonymous session to user",
                len(user_conversation.messages),
                extra={"user_id": str(user_id), "session_id": session_id[:8]},
            )
            return user_conversation
        else:
            # No existing user conversation - transfer ownership
            anon_conversation.user_id = user_id  # type: ignore[assignment]
            anon_conversation.session_id = None
            await self.session.commit()
            await self.session.refresh(anon_conversation)

            logger.info(
                "Transferred conversation %s from session to user",
                str(anon_conversation.id)[:8],
                extra={"user_id": str(user_id), "session_id": session_id[:8]},
            )
            return anon_conversation
