# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Usage reporting routes."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth import AuthContext
from billing.database import get_db
from billing.models import Customer, SaasApp, Subscription, UsageEvent
from billing.partition import require_saas_scopes
from billing.schemas import UsageBatchReport, UsageEventResponse, UsageReport

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/usage/{saas_id}", tags=["Usage"])


async def get_saas_app_or_404(saas_id: str, db: AsyncSession) -> SaasApp:
    """Get SaaS app or raise 404."""
    result = await db.execute(select(SaasApp).where(SaasApp.id == saas_id))
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )
    return saas_app


@router.post("/report", response_model=UsageEventResponse, status_code=status.HTTP_201_CREATED)
async def report_usage(
    saas_id: str,
    data: UsageReport,
    _auth: Annotated[AuthContext, Depends(require_saas_scopes("billing:usage:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UsageEvent:
    """Report a single usage event.

    Usage events are stored locally and batched for reporting to Stripe
    via a background worker (Celery).
    """
    await get_saas_app_or_404(saas_id, db)

    # Verify subscription exists and belongs to this SaaS app
    sub_result = await db.execute(
        select(Subscription)
        .join(Customer)
        .where(
            Subscription.id == data.subscription_id,
            Customer.saas_app_id == saas_id,
        )
    )
    subscription = sub_result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    if not subscription.stripe_subscription_item_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription does not support metered billing (no subscription item ID)",
        )

    # Check for idempotency (keys are scoped to the SaaS app)
    if data.idempotency_key:
        existing_result = await db.execute(
            select(UsageEvent).where(
                UsageEvent.saas_app_id == saas_id,
                UsageEvent.idempotency_key == data.idempotency_key,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            logger.info(f"Duplicate usage event: {data.idempotency_key}")
            return existing

    # Create usage event
    usage_event = UsageEvent(
        saas_app_id=saas_id,
        subscription_id=subscription.id,
        quantity=data.quantity,
        timestamp=data.timestamp or datetime.now(UTC),
        idempotency_key=data.idempotency_key,
        action=data.action,
        extra_data=data.metadata,
    )
    db.add(usage_event)
    await db.flush()
    await db.refresh(usage_event)

    logger.info(
        f"Recorded usage event: {usage_event.id} "
        f"(subscription={subscription.id}, quantity={data.quantity})"
    )
    return usage_event


@router.post(
    "/batch",
    response_model=list[UsageEventResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_usage_batch(
    saas_id: str,
    data: UsageBatchReport,
    _auth: Annotated[AuthContext, Depends(require_saas_scopes("billing:usage:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UsageEvent]:
    """Report multiple usage events in a batch.

    Usage events are stored locally and batched for reporting to Stripe
    via a background worker (Celery).
    """
    await get_saas_app_or_404(saas_id, db)

    events: list[UsageEvent] = []
    batch_keys: dict[str, UsageEvent] = {}

    for event_data in data.events:
        # Verify subscription exists and belongs to this SaaS app
        sub_result = await db.execute(
            select(Subscription)
            .join(Customer)
            .where(
                Subscription.id == event_data.subscription_id,
                Customer.saas_app_id == saas_id,
            )
        )
        subscription = sub_result.scalar_one_or_none()
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription {event_data.subscription_id} not found",
            )

        if not subscription.stripe_subscription_item_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Subscription {event_data.subscription_id} does not support metered billing",
            )

        # Check for idempotency (keys are scoped to the SaaS app, also inside the batch)
        if event_data.idempotency_key:
            if event_data.idempotency_key in batch_keys:
                events.append(batch_keys[event_data.idempotency_key])
                continue
            existing_result = await db.execute(
                select(UsageEvent).where(
                    UsageEvent.saas_app_id == saas_id,
                    UsageEvent.idempotency_key == event_data.idempotency_key,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                events.append(existing)
                continue

        # Create usage event
        usage_event = UsageEvent(
            saas_app_id=saas_id,
            subscription_id=subscription.id,
            quantity=event_data.quantity,
            timestamp=event_data.timestamp or datetime.now(UTC),
            idempotency_key=event_data.idempotency_key,
            action=event_data.action,
            extra_data=event_data.metadata,
        )
        db.add(usage_event)
        events.append(usage_event)
        if event_data.idempotency_key:
            batch_keys[event_data.idempotency_key] = usage_event

    await db.flush()
    for event in events:
        await db.refresh(event)

    logger.info(f"Recorded {len(events)} usage events for SaaS {saas_id}")
    return events
