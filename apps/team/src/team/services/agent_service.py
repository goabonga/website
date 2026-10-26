# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Agent lifecycle management service."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.models import Agent

logger = logging.getLogger(__name__)


class AgentService:
    """Manage agent lifecycle and configuration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_agents(self, team_id: UUID) -> list[Agent]:
        """Get all active agents for a team."""
        result = await self.db.execute(
            select(Agent).where(Agent.team_id == team_id, Agent.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def get_agent_by_role(self, team_id: UUID, role: str) -> Agent | None:
        """Find an agent by role within a team."""
        result = await self.db.execute(
            select(Agent).where(
                Agent.team_id == team_id,
                Agent.role == role,
                Agent.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()
