# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Remember the ids of the webhook events that were already processed.

The platform services deliver their webhooks at least once and retry them, and an
attacker who captured a signed request could send it again. The receivers therefore
look the event id up before acting and record it once the event is processed. The ids
live in Redis for a limited time; if Redis cannot be reached the event is processed
anyway, which is safe because the receivers only set the state described by the event.
"""

import redis.asyncio as redis

from knowledge.config import get_settings
from knowledge.logging import get_logger

logger = get_logger(__name__)


def _key(namespace: str, event_id: str) -> str:
    return f"{get_settings().redis_key_prefix}:events:{namespace}:{event_id}"


async def already_processed(namespace: str, event_id: str) -> bool:
    """Whether the event ``event_id`` of ``namespace`` was recorded as processed."""
    client = redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        return bool(await client.exists(_key(namespace, event_id)))
    except Exception as error:
        logger.warning("Event deduplication unavailable: %s", error)
        return False
    finally:
        await client.aclose()


async def mark_processed(namespace: str, event_id: str, ttl_seconds: int) -> None:
    """Record the event ``event_id`` of ``namespace`` as processed for ``ttl_seconds``."""
    client = redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await client.set(_key(namespace, event_id), "1", ex=ttl_seconds)
    except Exception as error:
        logger.warning("Event could not be recorded: %s", error)
    finally:
        await client.aclose()
