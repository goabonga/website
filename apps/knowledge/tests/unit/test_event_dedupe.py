# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the record of processed webhook events."""

from unittest.mock import AsyncMock, MagicMock, patch

from knowledge.services import event_dedupe


def _redis(**methods):
    client = MagicMock()
    client.aclose = AsyncMock()
    for name, value in methods.items():
        setattr(client, name, value)
    return client


def _patched(client):
    settings = MagicMock(redis_url="redis://test/0", redis_key_prefix="kn")
    return (
        patch.object(event_dedupe, "get_settings", return_value=settings),
        patch.object(event_dedupe.redis, "from_url", return_value=client),
    )


async def test_unknown_event_is_not_processed():
    client = _redis(exists=AsyncMock(return_value=0))
    first, second = _patched(client)
    with first, second:
        assert await event_dedupe.already_processed("billing", "evt-1") is False
    client.exists.assert_awaited_once_with("kn:events:billing:evt-1")
    client.aclose.assert_awaited_once()


async def test_recorded_event_is_processed():
    client = _redis(exists=AsyncMock(return_value=1))
    first, second = _patched(client)
    with first, second:
        assert await event_dedupe.already_processed("billing", "evt-1") is True


async def test_redis_failure_means_not_processed():
    client = _redis(exists=AsyncMock(side_effect=OSError("down")))
    first, second = _patched(client)
    with first, second:
        assert await event_dedupe.already_processed("billing", "evt-1") is False
    client.aclose.assert_awaited_once()


async def test_mark_records_the_event_for_a_limited_time():
    client = _redis(set=AsyncMock())
    first, second = _patched(client)
    with first, second:
        await event_dedupe.mark_processed("billing", "evt-1", 600)
    client.set.assert_awaited_once_with("kn:events:billing:evt-1", "1", ex=600)


async def test_mark_failure_is_not_fatal():
    client = _redis(set=AsyncMock(side_effect=OSError("down")))
    first, second = _patched(client)
    with first, second:
        await event_dedupe.mark_processed("billing", "evt-1", 600)
    client.aclose.assert_awaited_once()


async def test_namespaces_do_not_collide():
    client = _redis(exists=AsyncMock(return_value=0))
    first, second = _patched(client)
    with first, second:
        await event_dedupe.already_processed("billing", "same")
        await event_dedupe.already_processed("custom-domain", "same")
    keys = [call.args[0] for call in client.exists.await_args_list]
    assert keys == ["kn:events:billing:same", "kn:events:custom-domain:same"]
