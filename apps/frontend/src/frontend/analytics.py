# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Analytics tracking client for server-side event collection.

Sends events to the ``/collect`` endpoint of the analytics service.
Compatible with the frontend analytics SDK format.
"""

import asyncio
import contextlib
import logging
from typing import Any

import httpx
from fastapi import Request

logger = logging.getLogger(__name__)


class AnalyticsTracker:
    """Server-side analytics event tracker.

    Sends events asynchronously to the analytics collection endpoint.
    Events are queued and flushed when 10 are pending or after 5 seconds; each one
    is posted individually.
    """

    def __init__(
        self,
        analytics_url: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a tracker.

        Args:
            analytics_url: Base URL of the analytics service; empty disables tracking.
            transport: Optional httpx transport, used to deliver events without network.
        """
        self._endpoint = f"{analytics_url.rstrip('/')}/collect" if analytics_url else ""
        self._transport = transport
        self._queue: list[dict[str, Any]] = []
        self._flush_task: asyncio.Task | None = None
        self._max_queue_size = 10
        self._flush_interval = 5.0  # seconds

    @property
    def is_configured(self) -> bool:
        """Check if analytics tracking is configured."""
        return bool(self._endpoint)

    def track(
        self,
        event_type: str,
        event_data: dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        page_url: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Track an analytics event.

        Args:
            event_type: Type of event (e.g., "page_view", "api_error").
            event_data: Additional event data.
            user_id: Authenticated user ID (optional).
            session_id: Session ID for anonymous tracking.
            page_url: Page or endpoint URL.
            ip_address: Client IP address for geo tracking.
        """
        if not self.is_configured:
            return

        event: dict[str, Any] = {
            "event_type": event_type,
        }

        if page_url:
            event["page_url"] = page_url

        if event_data:
            event["event_data"] = event_data

        # Store user/session info separately for the batch
        self._queue.append(
            {
                "event": event,
                "user_id": user_id,
                "session_id": session_id,
                "ip_address": ip_address,
            }
        )

        logger.debug("Analytics event queued: %s", event_type)

        # Flush immediately if queue is full
        if len(self._queue) >= self._max_queue_size:
            asyncio.create_task(self.flush())
        elif self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._schedule_flush())

    async def _schedule_flush(self) -> None:
        """Schedule a delayed flush."""
        await asyncio.sleep(self._flush_interval)
        await self.flush()

    async def flush(self) -> None:
        """Send all queued events to the analytics server."""
        if not self._queue or not self.is_configured:
            return

        # Take all events from queue
        events_to_send = self._queue[:]
        self._queue.clear()

        # Group events by user_id/session_id for batching
        # For simplicity, send each event individually with its context
        async with httpx.AsyncClient(timeout=5.0, transport=self._transport) as client:
            for item in events_to_send:
                payload: dict[str, Any] = {
                    "events": [item["event"]],
                }

                if item.get("user_id"):
                    payload["user_id"] = item["user_id"]
                if item.get("session_id"):
                    payload["session_id"] = item["session_id"]
                if item.get("ip_address"):
                    payload["ip_address"] = item["ip_address"]

                try:
                    response = await client.post(
                        self._endpoint,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if response.status_code >= 400:
                        logger.warning(
                            "Analytics event failed: status=%d event=%s",
                            response.status_code,
                            item["event"]["event_type"],
                        )
                except Exception as e:
                    logger.warning(
                        "Analytics event send error: %s event=%s",
                        e,
                        item["event"]["event_type"],
                    )

    async def close(self) -> None:
        """Flush remaining events and close the tracker."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task

        await self.flush()


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request headers or connection."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return None
