# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the conversation cache feature."""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from backend.celery import celery_app
from backend.models.conversation import Conversation, Message
from backend.session.cache import ConversationCache
from backend.tasks import sync_conversations
from behave import given, then, when


class FakeRedis:
    """In-memory stand-in for the string commands used by the cache."""

    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value

    async def setex(self, key, ttl, value):
        self.data[key] = value

    async def expire(self, key, ttl):
        return key in self.data

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    async def scan_iter(self, pattern):
        prefix = pattern.rstrip("*")
        for key in list(self.data):
            if key.startswith(prefix):
                yield key

    async def aclose(self):
        pass


async def _refresh(obj):
    """Fill the columns PostgreSQL would generate."""
    now = datetime.now(UTC)
    obj.id = obj.id or uuid.uuid4()
    obj.created_at = now
    obj.updated_at = now
    if isinstance(obj, Conversation):
        obj.messages = []


@given("a conversation cache backed by an in-memory Redis")
def step_cache(context):
    context.db.refresh.side_effect = _refresh
    context.redis = FakeRedis()
    context.cache = ConversationCache(context.db)
    context.cache._redis = context.redis


def _create(context, session_id):
    data = asyncio.run(context.cache.create(session_id=session_id))
    context.conversation_id = uuid.UUID(data["id"])


@when('a cached conversation is created for the session "{session_id}"')
def step_create(context, session_id):
    _create(context, session_id)


@given('a cached conversation exists for the session "{session_id}"')
def step_exists(context, session_id):
    _create(context, session_id)


@when('the message "{content}" is added to the cached conversation with the role "{role}"')
@given('the message "{content}" is added to the cached conversation with the role "{role}"')
def step_add_message(context, content, role):
    asyncio.run(context.cache.add_message(context.conversation_id, role, content))


@then("the conversation should be readable from the cache")
def step_readable(context):
    data = asyncio.run(context.cache.get(context.conversation_id))
    assert data is not None and data["id"] == str(context.conversation_id)


@then("the cached conversation should contain {count:d} message")
def step_count(context, count):
    data = asyncio.run(context.cache.get(context.conversation_id))
    assert len(data["messages"]) == count


@then("the conversation should have no dirty flag")
def step_not_dirty(context):
    assert asyncio.run(context.cache.get_dirty_conversations()) == []


@then("the conversation should be listed as dirty")
def step_dirty(context):
    assert asyncio.run(context.cache.get_dirty_conversations()) == [str(context.conversation_id)]


@when("the dirty conversations are synced")
def step_sync(context):
    context.db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    context.db.add.reset_mock()
    context.synced = 0
    for conversation_id in asyncio.run(context.cache.get_dirty_conversations()):
        if asyncio.run(context.cache.sync_to_db(conversation_id)):
            context.synced += 1


@then("{count:d} conversation should have been synced")
def step_synced(context, count):
    assert context.synced == count


@then("the database should have received the conversation and {count:d} message")
def step_db_received(context, count):
    added = [call.args[0] for call in context.db.add.call_args_list]
    assert sum(isinstance(obj, Conversation) for obj in added) == 1
    assert sum(isinstance(obj, Message) for obj in added) == count
    context.db.commit.assert_awaited()


@when("the cached conversation is invalidated")
def step_invalidate(context):
    asyncio.run(context.cache.invalidate(context.conversation_id))


@then("the conversation should not be in the cache")
def step_not_cached(context):
    assert not any(key.startswith("conv:") for key in context.redis.data)


@then('the Celery beat schedule should run "{task}" every {seconds:d} seconds')
def step_schedule(context, task, seconds):
    entries = [e for e in celery_app.conf.beat_schedule.values() if e["task"] == task]
    assert len(entries) == 1 and entries[0]["schedule"] == seconds
    assert task in celery_app.tasks or sync_conversations.sync_dirty_conversations.name == task


@then('the Celery application should use the "{queue}" queue')
def step_queue(context, queue):
    assert celery_app.conf.task_default_queue == queue
