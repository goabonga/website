# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Provisioning events published to Redis."""

import json
from datetime import UTC, datetime

import redis

from custom_domain.config import settings
from custom_domain.logging import get_logger

logger = get_logger(__name__)


def publish_event(domain_id: str, event_type: str, payload: dict) -> None:
    """Publish an event to Redis for SSE streaming and keep it in the history.

    The history of a domain keeps the last ``EVENT_HISTORY_SIZE`` events for
    ``EVENT_HISTORY_TTL_SECONDS``. A Redis failure is logged and never raised: an
    event is informational and must not fail a provisioning step.
    """
    try:
        redis_client = redis.from_url(settings.redis_url)
        channel = f"domain:{domain_id}:events"

        event = {
            "type": event_type,
            "payload": {
                **payload,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

        redis_client.publish(channel, json.dumps(event))

        history_key = f"domain:{domain_id}:event_history"
        redis_client.lpush(history_key, json.dumps(event))
        redis_client.ltrim(history_key, 0, settings.event_history_size - 1)
        redis_client.expire(history_key, settings.event_history_ttl_seconds)

        redis_client.close()
    except Exception as e:
        logger.warning("Failed to publish event: %s", e)
