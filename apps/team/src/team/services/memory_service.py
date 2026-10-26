# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Memory service for shared knowledge and context."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.models import MemoryEntry

logger = logging.getLogger(__name__)


class MemoryService:
    """Manage shared knowledge and context for teams."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_recent_entries(self, team_id: UUID, limit: int = 50) -> list[MemoryEntry]:
        """Get recent memory entries for a team."""
        result = await self.db.execute(
            select(MemoryEntry)
            .where(MemoryEntry.team_id == team_id)
            .order_by(MemoryEntry.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_agent_memory(self, agent_id: UUID, limit: int = 50) -> list[MemoryEntry]:
        """Get memory entries for a specific agent."""
        result = await self.db.execute(
            select(MemoryEntry)
            .where(MemoryEntry.agent_id == agent_id)
            .order_by(MemoryEntry.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
