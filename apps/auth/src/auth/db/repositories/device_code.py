# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""DeviceCodeRepository — SQL access for Device Authorization (RFC 8628)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.oauth2 import DeviceCode


class DeviceCodeRepository:
    """Data access for :class:`DeviceCode` rows.

    Encapsulates every SQL query touching the ``device_codes`` table.
    Methods return SQLAlchemy model instances and never commit — the
    caller owns the transaction boundary.
    """

    async def find_by_device_code_hash(
        self,
        db: AsyncSession,
        device_code_hash: str,
    ) -> DeviceCode | None:
        """Fetch a device authorization by its hashed device code."""
        result = await db.execute(
            select(DeviceCode).where(DeviceCode.device_code_hash == device_code_hash)
        )
        return result.scalar_one_or_none()

    async def find_by_user_code(
        self,
        db: AsyncSession,
        user_code: str,
    ) -> DeviceCode | None:
        """Fetch a device authorization by its formatted user code."""
        result = await db.execute(select(DeviceCode).where(DeviceCode.user_code == user_code))
        return result.scalar_one_or_none()

    async def list_expired(
        self,
        db: AsyncSession,
        now: datetime,
    ) -> Sequence[DeviceCode]:
        """Return every device code whose ``expires_at`` is strictly before ``now``."""
        result = await db.execute(select(DeviceCode).where(DeviceCode.expires_at < now))
        return result.scalars().all()

    async def add(self, db: AsyncSession, device: DeviceCode) -> None:
        """Stage a new device code row and flush."""
        db.add(device)
        await db.flush()

    async def delete(self, db: AsyncSession, device: DeviceCode) -> None:
        """Stage a device code deletion (no commit)."""
        await db.delete(device)
