# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""WebhookRepository — SQL access for TenantWebhook and WebhookDelivery rows."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.tenant import TenantWebhook, WebhookDelivery


class WebhookRepository:
    """Data access for :class:`TenantWebhook` and :class:`WebhookDelivery` rows.

    Encapsulates every SQL query touching the ``tenant_webhooks`` and
    ``webhook_deliveries`` tables. Methods return SQLAlchemy model instances
    and never commit — the caller (typically :class:`WebhookService`) owns
    the transaction boundary.
    """

    # ------------------------------------------------------------------
    # Webhook reads
    # ------------------------------------------------------------------

    async def find_for_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        webhook_id: uuid.UUID,
    ) -> TenantWebhook | None:
        """Fetch a webhook by ID scoped to ``tenant_id``."""
        result = await db.execute(
            select(TenantWebhook).where(
                TenantWebhook.id == webhook_id,
                TenantWebhook.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_matching_subscribed(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        patterns: list[str],
    ) -> Sequence[TenantWebhook]:
        """List active webhooks for ``tenant_id`` whose ``events`` overlap ``patterns``.

        Ordered by ``created_at`` ascending so the oldest subscription is
        dispatched first. Used by :class:`WebhookService` when fanning out an
        event to matching subscriptions.
        """
        result = await db.execute(
            select(TenantWebhook)
            .where(
                TenantWebhook.tenant_id == tenant_id,
                TenantWebhook.is_active.is_(True),
                TenantWebhook.events.overlap(patterns),
            )
            .order_by(TenantWebhook.created_at)
        )
        return result.scalars().all()

    async def count_by_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> int:
        """Count webhooks registered for ``tenant_id``."""
        result = await db.execute(
            select(func.count())
            .select_from(TenantWebhook)
            .where(TenantWebhook.tenant_id == tenant_id)
        )
        return result.scalar() or 0

    async def list_by_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[TenantWebhook]:
        """List webhooks for ``tenant_id`` ordered by creation date desc."""
        result = await db.execute(
            select(TenantWebhook)
            .where(TenantWebhook.tenant_id == tenant_id)
            .order_by(TenantWebhook.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_all_by_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Sequence[TenantWebhook]:
        """List every webhook for ``tenant_id`` ordered by creation date desc."""
        result = await db.execute(
            select(TenantWebhook)
            .where(TenantWebhook.tenant_id == tenant_id)
            .order_by(TenantWebhook.created_at.desc())
        )
        return result.scalars().all()

    async def list_recent_deliveries(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
        *,
        limit: int = 20,
    ) -> Sequence[WebhookDelivery]:
        """List the N most recent delivery attempts for ``webhook_id``."""
        result = await db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Delivery reads
    # ------------------------------------------------------------------

    async def count_deliveries(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
    ) -> int:
        """Count delivery attempts for ``webhook_id``."""
        result = await db.execute(
            select(func.count())
            .select_from(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
        )
        return result.scalar() or 0

    async def list_deliveries(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[WebhookDelivery]:
        """List delivery attempts for ``webhook_id`` ordered by creation date desc."""
        result = await db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def find_delivery_for_webhook(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
        delivery_id: uuid.UUID,
    ) -> WebhookDelivery | None:
        """Fetch a delivery by ID scoped to ``webhook_id``."""
        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.webhook_id == webhook_id,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def add(self, db: AsyncSession, instance: object) -> None:
        """Stage a new row and flush so generated columns are populated."""
        db.add(instance)
        await db.flush()

    async def stage(self, db: AsyncSession, instance: object) -> object:
        """Stage a new row without flushing.

        Used by fan-out dispatch that stages one :class:`WebhookDelivery` per
        subscribed webhook and shares a single final flush.
        """
        db.add(instance)
        return instance

    async def delete(self, db: AsyncSession, instance: object) -> None:
        """Stage a row deletion (no commit)."""
        await db.delete(instance)

    async def flush(self, db: AsyncSession) -> None:
        """Flush pending changes (no commit)."""
        await db.flush()
