# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for admin dashboard and conversation management scenarios."""

import uuid
from unittest.mock import AsyncMock

from behave import given, when
from internal.models.conversation import Conversation, Message

# --- Seed data helpers ---


@given('a conversation exists with title "{title}"')
def step_conversation_with_title(context, title):
    async def _create():
        async with context.session_maker() as session:
            conv = Conversation(
                id=uuid.uuid4(),
                user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                title=title,
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            context.conversation_id = str(conv.id)
            context.created_ids.append(str(conv.id))
            return conv

    context.loop.run_until_complete(_create())


@given('another conversation exists with title "{title}"')
def step_another_conversation_with_title(context, title):
    async def _create():
        async with context.session_maker() as session:
            conv = Conversation(
                id=uuid.uuid4(),
                user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                title=title,
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            context.created_ids.append(str(conv.id))
            return conv

    context.loop.run_until_complete(_create())


@given('a conversation exists with session id "{session_id}"')
def step_conversation_with_session_id(context, session_id):
    async def _create():
        async with context.session_maker() as session:
            conv = Conversation(
                id=uuid.uuid4(),
                session_id=session_id,
                title="Anonymous Session",
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            context.conversation_id = str(conv.id)
            context.created_ids.append(str(conv.id))
            return conv

    context.loop.run_until_complete(_create())


@given('the conversation has a message with role "{role}" and content "{content}"')
def step_conversation_has_message(context, role, content):
    async def _create():
        async with context.session_maker() as session:
            msg = Message(
                id=uuid.uuid4(),
                conversation_id=uuid.UUID(context.conversation_id),
                role=role,
                content=content,
            )
            session.add(msg)
            await session.commit()

    context.loop.run_until_complete(_create())


# --- Auth client mock setup ---


@given("the auth client returns a user for the dashboard")
def step_auth_client_dashboard(context):
    context.mock_auth_client.get_user = AsyncMock(return_value=None)


@given("the auth client returns user info for conversation owner")
def step_auth_client_user_info(context):
    context.mock_auth_client.get_user = AsyncMock(
        return_value={
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "owner@test.local",
            "name": "Conversation Owner",
        }
    )


# --- Dynamic path request steps ---


@when("I view the conversation detail")
def step_view_conversation_detail(context):
    from httpx import ASGITransport, AsyncClient

    cookies = {"access_token": "test-token"} if context.authenticated else {}
    conversation_id = getattr(context, "conversation_id", "00000000-0000-0000-0000-000000000099")
    path = f"/conversations/{conversation_id}"

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            return await client.get(path)

    context.response = context.loop.run_until_complete(_do_request())


@when("I delete the conversation")
def step_delete_conversation(context):
    from httpx import ASGITransport, AsyncClient

    cookies = {"access_token": "test-token"} if context.authenticated else {}
    conversation_id = getattr(context, "conversation_id", "00000000-0000-0000-0000-000000000099")
    path = f"/conversations/{conversation_id}/delete"

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            return await client.post(path)

    context.response = context.loop.run_until_complete(_do_request())


@when("I bulk delete the created conversations")
def step_bulk_delete_conversations(context):
    from httpx import ASGITransport, AsyncClient

    cookies = {"access_token": "test-token"} if context.authenticated else {}

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            # Use multipart form data for list fields
            files = [("conversation_ids", (None, str(cid))) for cid in context.created_ids]
            return await client.post("/conversations/bulk-delete", files=files)

    context.response = context.loop.run_until_complete(_do_request())
