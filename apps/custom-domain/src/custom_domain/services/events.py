# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Provisioning events published to Redis."""

import json
import uuid
from datetime import UTC, datetime

import redis

from custom_domain.config import settings
from custom_domain.logging import get_logger

logger = get_logger(__name__)


def webhook_event_name(event_type: str, payload: dict) -> str | None:
    """Map a progress event to the name of the webhook it triggers, if any.

    ``domain.status_changed`` follows every status change, ``domain.active`` the end
    of a successful provisioning, ``domain.failed`` an error and ``domain.deleted``
    the end of a deprovisioning. Step events are not sent.
    """
    if event_type == "status_change":
        return "domain.status_changed"
    if event_type == "completed":
        return "domain.deleted" if payload.get("deleted") else "domain.active"
    if event_type == "error":
        return "domain.failed"
    return None


def notify_webhook(domain_id: str, event_type: str, payload: dict) -> None:
    """Queue the delivery of the webhook that matches an event.

    The delivery task looks the client up and does nothing when it has no webhook.
    A broker failure is logged and never raised.
    """
    name = webhook_event_name(event_type, payload)
    if name is None:
        return
    try:
        from custom_domain.tasks.webhooks import deliver_webhook

        deliver_webhook.apply_async(
            args=[domain_id, name, payload, str(uuid.uuid4()), datetime.now(UTC).isoformat()],
            retry=False,
        )
    except Exception as e:
        logger.warning("Failed to queue webhook %s: %s", name, e)


def publish_event(domain_id: str, event_type: str, payload: dict) -> None:
    """Publish an event to Redis for SSE streaming and keep it in the history.

    The history of a domain keeps the last ``EVENT_HISTORY_SIZE`` events for
    ``EVENT_HISTORY_TTL_SECONDS``. A Redis failure is logged and never raised: an
    event is informational and must not fail a provisioning step. Status changes,
    completions and errors also trigger the client's webhook (``notify_webhook``).
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

    notify_webhook(domain_id, event_type, payload)
