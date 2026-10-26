# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/events.py."""

import json
from unittest.mock import MagicMock, patch

from custom_domain.config import settings
from custom_domain.services.events import publish_event


class TestPublishEvent:
    """Events go to a channel and to a bounded, expiring history."""

    def test_publishes_and_keeps_history(self, monkeypatch):
        monkeypatch.setattr(settings, "event_history_size", 5)
        monkeypatch.setattr(settings, "event_history_ttl_seconds", 120)
        with patch("custom_domain.services.events.redis") as mock_redis:
            client = mock_redis.from_url.return_value
            publish_event("dom-1", "step_started", {"step": "certbot"})

        channel, message = client.publish.call_args[0]
        assert channel == "domain:dom-1:events"
        assert json.loads(message)["type"] == "step_started"
        assert json.loads(message)["payload"]["step"] == "certbot"
        client.lpush.assert_called_once()
        assert client.lpush.call_args[0][0] == "domain:dom-1:event_history"
        client.ltrim.assert_called_once_with("domain:dom-1:event_history", 0, 4)
        client.expire.assert_called_once_with("domain:dom-1:event_history", 120)
        client.close.assert_called_once()

    def test_uses_the_configured_redis(self, monkeypatch):
        monkeypatch.setattr(settings, "redis_url", "redis://events.invalid:6379/3")
        with patch("custom_domain.services.events.redis") as mock_redis:
            publish_event("dom-1", "completed", {})
        mock_redis.from_url.assert_called_once_with("redis://events.invalid:6379/3")

    def test_redis_failure_is_swallowed(self):
        with patch("custom_domain.services.events.redis") as mock_redis:
            mock_redis.from_url = MagicMock(side_effect=ConnectionError("down"))
            publish_event("dom-1", "completed", {})
