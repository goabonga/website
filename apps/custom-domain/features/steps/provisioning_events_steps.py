# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the provisioning status and events feature."""

import json
from unittest.mock import AsyncMock, MagicMock

from behave import given, then
from environment import start_patch


class FakePubSub:
    """Delivers a fixed list of Redis pub/sub messages, then nothing."""

    def __init__(self, events):
        self._messages = [
            {"type": "message", "data": json.dumps({"type": e["type"], "payload": e["payload"]})}
            for e in events
        ]
        self.subscribe = AsyncMock()
        self.unsubscribe = AsyncMock()
        self.close = AsyncMock()

    async def get_message(self, ignore_subscribe_messages=True):
        return self._messages.pop(0) if self._messages else None


def install_redis(context, history=(), live=()):
    client = MagicMock()
    client.lrange = AsyncMock(return_value=list(history))
    client.llen = AsyncMock(return_value=len(history))
    client.close = AsyncMock()
    client.pubsub.return_value = FakePubSub(live)
    start_patch(context, "custom_domain.routes.events.redis.from_url", return_value=client)


@given('Redis holds these events for "{name}"')
def step_history(context, name):
    history = [
        json.dumps(
            {
                "type": row["type"],
                "payload": {
                    "step": row["step"] or None,
                    "message": row["message"],
                    "timestamp": row["timestamp"],
                },
            }
        )
        for row in context.table
    ]
    install_redis(context, history=history)


@given("Redis publishes no live event")
def step_no_live(context):
    install_redis(context)


@given("Redis publishes these live events")
def step_live(context):
    install_redis(
        context,
        live=[
            {"type": row["type"], "payload": json.loads(row["payload"])} for row in context.table
        ],
    )


@then("the progress is {percent:d} percent")
def step_progress(context, percent):
    assert context.response.json()["progress"]["percentage"] == percent


@then("all {count:d} provisioning steps are completed")
def step_steps_completed(context, count):
    assert len(context.response.json()["progress"]["steps_completed"]) == count


@then('the current step is "{step}"')
def step_current_step(context, step):
    assert context.response.json()["progress"]["current_step"] == step


@then('the stream carries the events "{names}"')
def step_stream_events(context, names):
    received = [
        line.split(":", 1)[1].strip()
        for line in context.response.text.splitlines()
        if line.startswith("event:")
    ]
    assert received == [name.strip() for name in names.split(",")], context.response.text
