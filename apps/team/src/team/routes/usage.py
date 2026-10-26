# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Usage reporting routes."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from team.auth import AuthContext, require_scopes
from team.database import get_db
from team.models import ExecutionLog, Team
from team.schemas import UsageBatchReport, UsageEventResponse, UsageReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usage/{team_id}", tags=["Usage"])


def _to_naive(ts: datetime | None) -> datetime:
    """Convert an optional timestamp to a naive UTC datetime."""
    if ts is None:
        return datetime.now(UTC).replace(tzinfo=None)
    if ts.tzinfo is not None:
        return ts.replace(tzinfo=None)
    return ts


async def get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    return team


@router.post("/report", response_model=UsageEventResponse, status_code=status.HTTP_201_CREATED)
async def report_usage(
    team_id: str,
    data: UsageReport,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExecutionLog:
    """Report a task execution event."""

    await get_team_or_404(team_id, db)

    log = ExecutionLog(
        team_id=team_id,
        agent_id=data.agent_id,
        task_id=data.task_id,
        event_type=data.action,
        details=data.details,
        created_at=_to_naive(data.timestamp),
    )

    db.add(log)
    await db.flush()
    await db.refresh(log)

    logger.info(f"Usage reported for team {team_id}: {data.action}")

    return log


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def batch_report_usage(
    team_id: str,
    data: UsageBatchReport,
    _auth: Annotated[AuthContext, Depends(require_scopes("team:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Batch report agent activity."""

    await get_team_or_404(team_id, db)

    logs = []
    for event in data.events:
        log = ExecutionLog(
            team_id=team_id,
            agent_id=event.agent_id,
            task_id=event.task_id,
            event_type=event.action,
            details=event.details,
            created_at=_to_naive(event.timestamp),
        )
        db.add(log)
        logs.append(log)

    await db.flush()

    logger.info(f"Batch usage reported for team {team_id}: {len(logs)} events")

    return {"created": len(logs)}
