# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for ChatService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.chat.service import ChatService


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
def service(mock_session):
    """Return a ChatService with a mocked session."""
    return ChatService(mock_session)


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
    conv.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    conv.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    conv.messages = []
    return conv


@pytest.fixture
def mock_message(conversation_id):
    """Return a mock Message object."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.conversation_id = conversation_id
    msg.role = "user"
    msg.content = "Hello"
    msg.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    return msg


# ---------------------------------------------------------------------------
# create_conversation
# ---------------------------------------------------------------------------


async def test_create_conversation(service, mock_session, user_id, session_id):
    """create_conversation creates and returns a conversation."""
    await service.create_conversation(user_id=user_id, session_id=session_id, title="My Chat")

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once()

    created = mock_session.add.call_args[0][0]
    assert created.user_id == user_id
    assert created.session_id == session_id
    assert created.title == "My Chat"


# ---------------------------------------------------------------------------
# get_or_create_conversation
# ---------------------------------------------------------------------------


async def test_get_or_create_conversation_returns_existing(
    service, mock_session, user_id, mock_conversation
):
    """get_or_create_conversation returns existing conversation when found."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    conversation, created = await service.get_or_create_conversation(user_id=user_id)

    assert conversation is mock_conversation
    assert created is False
    mock_session.execute.assert_awaited_once()


async def test_get_or_create_conversation_creates_new(service, mock_session, user_id):
    """get_or_create_conversation creates new conversation when not found."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    conversation, created = await service.get_or_create_conversation(user_id=user_id)

    assert created is True
    # create_conversation calls add + commit + refresh
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once()


async def test_get_or_create_conversation_ephemeral(service, mock_session):
    """get_or_create_conversation with no user_id and no session_id creates ephemeral."""
    conversation, created = await service.get_or_create_conversation(user_id=None, session_id=None)

    assert created is True
    # Should have called create_conversation (add + commit + refresh) without execute
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once()
    mock_session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_conversation
# ---------------------------------------------------------------------------


async def test_get_conversation_found(
    service, mock_session, conversation_id, user_id, mock_conversation
):
    """get_conversation returns conversation when found."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.get_conversation(conversation_id, user_id=user_id)

    assert result is mock_conversation
    mock_session.execute.assert_awaited_once()


async def test_get_conversation_not_found(service, mock_session, conversation_id):
    """get_conversation returns None when not found."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await service.get_conversation(conversation_id)

    assert result is None


# ---------------------------------------------------------------------------
# list_conversations
# ---------------------------------------------------------------------------


async def test_list_conversations(service, mock_session, user_id, mock_conversation):
    """list_conversations returns a list of conversations."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_conversation]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock

    result = await service.list_conversations(user_id=user_id)

    assert result == [mock_conversation]
    mock_session.execute.assert_awaited_once()


async def test_list_conversations_no_user_no_session(service, mock_session):
    """list_conversations with no user/session returns empty list."""
    result = await service.list_conversations(user_id=None, session_id=None)

    assert result == []
    mock_session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# add_message
# ---------------------------------------------------------------------------


async def test_add_message(service, mock_session, conversation_id):
    """add_message creates and returns a message."""
    await service.add_message(conversation_id, "user", "Hello")

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once()

    created = mock_session.add.call_args[0][0]
    assert created.conversation_id == conversation_id
    assert created.role == "user"
    assert created.content == "Hello"


# ---------------------------------------------------------------------------
# get_conversation_history
# ---------------------------------------------------------------------------


async def test_get_conversation_history(service, mock_session, conversation_id):
    """get_conversation_history returns list of dicts."""
    msg1 = MagicMock()
    msg1.role = "user"
    msg1.content = "Hello"
    msg2 = MagicMock()
    msg2.role = "assistant"
    msg2.content = "Hi there!"

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [msg1, msg2]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock

    history = await service.get_conversation_history(conversation_id)

    assert history == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]


# ---------------------------------------------------------------------------
# update_title
# ---------------------------------------------------------------------------


async def test_update_title(service, mock_session, conversation_id, user_id, mock_conversation):
    """update_title updates and returns the conversation."""
    # Mock get_conversation (which calls session.execute)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.update_title(conversation_id, "New Title", user_id=user_id)

    assert result is mock_conversation
    assert mock_conversation.title == "New Title"
    mock_session.commit.assert_awaited()
    mock_session.refresh.assert_awaited()


async def test_update_title_not_found(service, mock_session, conversation_id):
    """update_title returns None when conversation not found."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await service.update_title(conversation_id, "New Title")

    assert result is None


# ---------------------------------------------------------------------------
# update_summary
# ---------------------------------------------------------------------------


async def test_update_summary(service, mock_session, conversation_id, user_id, mock_conversation):
    """update_summary updates the summary and returns the conversation."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.update_summary(conversation_id, "Updated summary", user_id=user_id)

    assert result is mock_conversation
    assert mock_conversation.summary == "Updated summary"
    mock_session.commit.assert_awaited()
    mock_session.refresh.assert_awaited()


# ---------------------------------------------------------------------------
# delete_conversation
# ---------------------------------------------------------------------------


async def test_delete_conversation(
    service, mock_session, conversation_id, user_id, mock_conversation
):
    """delete_conversation deletes and returns True."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.delete_conversation(conversation_id, user_id=user_id)

    assert result is True
    mock_session.delete.assert_awaited_once_with(mock_conversation)
    mock_session.commit.assert_awaited()


async def test_delete_conversation_not_found(service, mock_session, conversation_id):
    """delete_conversation returns False when not found."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await service.delete_conversation(conversation_id)

    assert result is False
    mock_session.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# reset_conversation
# ---------------------------------------------------------------------------


async def test_reset_conversation(service, mock_session, user_id, mock_conversation):
    """reset_conversation deletes the conversation and returns True."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.reset_conversation(user_id=user_id)

    assert result is True
    mock_session.delete.assert_awaited_once_with(mock_conversation)
    mock_session.commit.assert_awaited()


async def test_reset_conversation_not_found(service, mock_session, user_id):
    """reset_conversation returns False when no conversation exists."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await service.reset_conversation(user_id=user_id)

    assert result is False
    mock_session.delete.assert_not_awaited()


async def test_reset_conversation_no_user_no_session(service, mock_session):
    """reset_conversation returns False with no user/session."""
    result = await service.reset_conversation(user_id=None, session_id=None)

    assert result is False
    mock_session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# archive_conversation
# ---------------------------------------------------------------------------


async def test_archive_conversation(service, mock_session, user_id, mock_conversation):
    """archive_conversation sets archived_at and returns conversation."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.archive_conversation(user_id=user_id)

    assert result is mock_conversation
    assert mock_conversation.archived_at is not None
    mock_session.commit.assert_awaited()
    mock_session.refresh.assert_awaited()


async def test_archive_conversation_no_user_no_session(service, mock_session):
    """archive_conversation returns None with no user/session."""
    result = await service.archive_conversation(user_id=None, session_id=None)

    assert result is None
    mock_session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# migrate_conversation
# ---------------------------------------------------------------------------


async def test_migrate_conversation_transfer_ownership(service, mock_session, session_id, user_id):
    """migrate_conversation transfers ownership when no existing user conversation."""
    anon_conv = MagicMock()
    anon_conv.id = uuid.uuid4()
    anon_conv.user_id = None
    anon_conv.session_id = session_id
    anon_conv.messages = []

    # First execute: find anonymous conversation -> found
    # Second execute: find user conversation -> not found
    result_anon = MagicMock()
    result_anon.scalar_one_or_none.return_value = anon_conv
    result_user = MagicMock()
    result_user.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [result_anon, result_user]

    result = await service.migrate_conversation(session_id, user_id)

    assert result is anon_conv
    assert anon_conv.user_id == user_id
    assert anon_conv.session_id is None
    mock_session.commit.assert_awaited()
    mock_session.refresh.assert_awaited()


async def test_migrate_conversation_merge(service, mock_session, session_id, user_id):
    """migrate_conversation merges conversations when user already has one."""
    anon_msg = MagicMock()
    anon_msg.conversation_id = uuid.uuid4()

    anon_conv = MagicMock()
    anon_conv.id = uuid.uuid4()
    anon_conv.user_id = None
    anon_conv.session_id = session_id
    anon_conv.messages = [anon_msg]

    user_conv = MagicMock()
    user_conv.id = uuid.uuid4()
    user_conv.user_id = user_id
    user_conv.messages = []

    # First execute: find anonymous conversation -> found
    # Second execute: find user conversation -> found
    result_anon = MagicMock()
    result_anon.scalar_one_or_none.return_value = anon_conv
    result_user = MagicMock()
    result_user.scalar_one_or_none.return_value = user_conv

    mock_session.execute.side_effect = [result_anon, result_user]

    result = await service.migrate_conversation(session_id, user_id)

    assert result is user_conv
    # Message should have been moved to user conversation
    assert anon_msg.conversation_id == user_conv.id
    # Anonymous conversation should be deleted
    mock_session.delete.assert_awaited_once_with(anon_conv)
    mock_session.commit.assert_awaited()
    mock_session.refresh.assert_awaited()


async def test_migrate_conversation_no_anonymous(service, mock_session, session_id, user_id):
    """migrate_conversation returns None when no anonymous conversation exists."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await service.migrate_conversation(session_id, user_id)

    assert result is None


# ---------------------------------------------------------------------------
# Additional tests for branch coverage
# ---------------------------------------------------------------------------


async def test_get_or_create_with_session_id_existing(
    service, mock_session, session_id, mock_conversation
):
    """get_or_create_conversation with session_id returns existing conversation."""
    mock_conversation.session_id = session_id
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    conversation, created = await service.get_or_create_conversation(
        user_id=None, session_id=session_id
    )

    assert conversation is mock_conversation
    assert created is False
    mock_session.execute.assert_awaited_once()


async def test_get_conversation_with_session_id_filter(
    service, mock_session, conversation_id, session_id, mock_conversation
):
    """get_conversation with session_id filters by session_id."""
    mock_conversation.session_id = session_id
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.get_conversation(conversation_id, user_id=None, session_id=session_id)

    assert result is mock_conversation
    mock_session.execute.assert_awaited_once()


async def test_list_conversations_with_session_id(
    service, mock_session, session_id, mock_conversation
):
    """list_conversations with session_id returns matching conversations."""
    mock_conversation.session_id = session_id
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_conversation]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock

    result = await service.list_conversations(user_id=None, session_id=session_id)

    assert result == [mock_conversation]
    mock_session.execute.assert_awaited_once()


async def test_get_conversation_history_with_limit(service, mock_session, conversation_id):
    """get_conversation_history with limit applies the limit."""
    msg1 = MagicMock()
    msg1.role = "user"
    msg1.content = "Hello"

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [msg1]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock

    history = await service.get_conversation_history(conversation_id, limit=10)

    assert history == [{"role": "user", "content": "Hello"}]
    mock_session.execute.assert_awaited_once()


async def test_update_summary_not_found(service, mock_session, conversation_id):
    """update_summary returns None when conversation not found."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await service.update_summary(conversation_id, "New summary")

    assert result is None


async def test_reset_conversation_with_session_id(
    service, mock_session, session_id, mock_conversation
):
    """reset_conversation with session_id deletes the matching conversation."""
    mock_conversation.session_id = session_id
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.reset_conversation(user_id=None, session_id=session_id)

    assert result is True
    mock_session.delete.assert_awaited_once_with(mock_conversation)
    mock_session.commit.assert_awaited()


async def test_archive_conversation_with_session_id(
    service, mock_session, session_id, mock_conversation
):
    """archive_conversation with session_id archives the matching conversation."""
    mock_conversation.session_id = session_id
    mock_conversation.archived_at = None
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_conversation
    mock_session.execute.return_value = result_mock

    result = await service.archive_conversation(user_id=None, session_id=session_id)

    assert result is mock_conversation
    assert mock_conversation.archived_at is not None
    mock_session.commit.assert_awaited()
    mock_session.refresh.assert_awaited()


async def test_archive_no_active_conversation(service, mock_session, user_id):
    """archive_conversation returns None when no active conversation exists."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await service.archive_conversation(user_id=user_id)

    assert result is None
