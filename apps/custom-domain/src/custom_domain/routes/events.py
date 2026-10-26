# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SSE and polling endpoints for domain provisioning progress."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from custom_domain.auth import AuthContext
from custom_domain.config import settings
from custom_domain.database import get_db
from custom_domain.logging import get_logger
from custom_domain.models import CustomDomain, DomainStatus
from custom_domain.models.enums import ProvisioningStep
from custom_domain.routes.access import require_client_scopes
from custom_domain.schemas import (
    DomainStatusResponse,
    EventHistoryItem,
    EventHistoryResponse,
    ProgressStep,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/domains", tags=["events"])


async def get_domain_or_404(
    db: AsyncSession,
    domain_id: UUID,
    auth: AuthContext,
) -> CustomDomain:
    """Get a domain by ID or raise 404."""
    result = await db.execute(select(CustomDomain).where(CustomDomain.id == domain_id))
    domain = result.scalar_one_or_none()

    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found",
        )

    if not auth.is_admin and domain.client_id != auth.user.client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return domain


def get_progress_for_status(status: DomainStatus) -> ProgressStep:
    """Get progress information based on domain status."""
    all_steps = [
        ProvisioningStep.DNS_CHECK.value,
        ProvisioningStep.NGINX_HTTP.value,
        ProvisioningStep.CERTBOT.value,
        ProvisioningStep.NGINX_HTTPS.value,
    ]

    if status == DomainStatus.PENDING:
        return ProgressStep(
            current_step=None,
            steps_completed=[],
            steps_remaining=all_steps,
            percentage=0,
        )
    elif status == DomainStatus.DNS_VERIFYING:
        return ProgressStep(
            current_step=ProvisioningStep.DNS_CHECK.value,
            steps_completed=[],
            steps_remaining=all_steps,
            percentage=10,
        )
    elif status == DomainStatus.DNS_VERIFIED:
        return ProgressStep(
            current_step=None,
            steps_completed=[ProvisioningStep.DNS_CHECK.value],
            steps_remaining=all_steps[1:],
            percentage=25,
        )
    elif status == DomainStatus.SSL_PROVISIONING:
        return ProgressStep(
            current_step=ProvisioningStep.CERTBOT.value,
            steps_completed=[ProvisioningStep.DNS_CHECK.value, ProvisioningStep.NGINX_HTTP.value],
            steps_remaining=[ProvisioningStep.NGINX_HTTPS.value],
            percentage=60,
        )
    elif status == DomainStatus.ACTIVE:
        return ProgressStep(
            current_step=None,
            steps_completed=all_steps,
            steps_remaining=[],
            percentage=100,
        )
    else:
        return ProgressStep(percentage=0)


@router.get("/{domain_id}/status", response_model=DomainStatusResponse)
async def get_domain_status(
    domain_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:read")),
):
    """Get current domain status for polling."""
    domain = await get_domain_or_404(db, domain_id, auth)

    progress = get_progress_for_status(domain.status)

    return DomainStatusResponse(
        id=domain.id,
        domain=domain.domain,
        status=domain.status,
        progress=progress,
        last_event=None,  # Would come from Redis event history
        error=domain.error_message,
        retry_count=domain.retry_count,
        next_retry_at=None,
    )


@router.get("/{domain_id}/events")
async def domain_events(
    domain_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:read")),
):
    """Stream domain provisioning events via SSE."""
    domain = await get_domain_or_404(db, domain_id, auth)

    async def event_generator():
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        channel = f"domain:{domain_id}:events"

        await pubsub.subscribe(channel)

        try:
            # Send initial state
            progress = get_progress_for_status(domain.status)
            yield {
                "event": "initial_state",
                "data": json.dumps(
                    {
                        "domain": domain.domain,
                        "status": domain.status.value,
                        "progress": progress.model_dump(),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                ),
            }

            # If already complete or failed, send that and exit
            if domain.status in (DomainStatus.ACTIVE, DomainStatus.FAILED):
                event_type = "completed" if domain.status == DomainStatus.ACTIVE else "error"
                yield {
                    "event": event_type,
                    "data": json.dumps(
                        {
                            "status": domain.status.value,
                            "error": domain.error_message,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ),
                }
                return

            # Listen for events with heartbeat
            heartbeat_interval = settings.sse_heartbeat_interval
            last_heartbeat = asyncio.get_event_loop().time()

            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=settings.sse_poll_interval_seconds,
                    )

                    if message and message["type"] == "message":
                        event_data = json.loads(message["data"])
                        yield {
                            "event": event_data["type"],
                            "data": json.dumps(event_data["payload"]),
                        }

                        if event_data["type"] in ("completed", "error"):
                            break

                except TimeoutError:
                    pass

                # Send heartbeat
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps(
                            {
                                "timestamp": datetime.now(UTC).isoformat(),
                            }
                        ),
                    }
                    last_heartbeat = now

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await redis_client.close()

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{domain_id}/events/history", response_model=EventHistoryResponse)
async def get_event_history(
    domain_id: UUID,
    limit: int = 50,
    since: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:read")),
):
    """Get event history for a domain."""
    await get_domain_or_404(db, domain_id, auth)

    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    try:
        history_key = f"domain:{domain_id}:event_history"
        raw_events = await redis_client.lrange(
            history_key, 0, min(limit, settings.event_history_size) - 1
        )

        events = []
        for raw in raw_events:
            event = json.loads(raw)
            payload = event.get("payload", {})
            event_time = datetime.fromisoformat(payload.get("timestamp", "").replace("Z", "+00:00"))

            if since and event_time < since:
                continue

            events.append(
                EventHistoryItem(
                    type=event.get("type", "unknown"),
                    step=payload.get("step"),
                    message=payload.get("message", ""),
                    timestamp=event_time,
                )
            )

        total_count = await redis_client.llen(history_key)
        has_more = total_count > len(events)

        oldest = events[-1].timestamp if events else None

        return EventHistoryResponse(
            events=events,
            has_more=has_more,
            oldest_timestamp=oldest,
        )

    finally:
        await redis_client.close()
