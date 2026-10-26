# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Reports API for Reachy Mini."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from reachy_mini_api.auth import AuthContext, require_scopes
from reachy_mini_api.logging import get_logger, log_action

logger = get_logger(__name__)
router = APIRouter()


class DailyReport(BaseModel):
    """Daily report model."""

    date: str
    summary: str
    tasks_completed: int
    tasks_pending: int
    notifications: list[str]
    weather: str | None = None
    calendar_events: list[str] = []


class QuickUpdate(BaseModel):
    """Quick update for Reachy to announce."""

    message: str
    priority: str = "normal"  # low, normal, high
    category: str = "general"


@router.get("/daily", response_model=DailyReport)
async def get_daily_report(
    auth: AuthContext = Depends(require_scopes("reachy:reports:read")),
):
    """Get today's daily report for Reachy to announce."""
    log_action(logger, "get_daily_report", user_id=auth.user_id)

    # TODO: Implement actual data fetching from various sources
    return DailyReport(
        date=datetime.now().strftime("%Y-%m-%d"),
        summary="Today is looking productive!",
        tasks_completed=5,
        tasks_pending=3,
        notifications=[
            "New email from the team",
            "Reminder: Meeting at 2 PM",
        ],
        weather="Sunny, 22°C",
        calendar_events=[
            "10:00 - Team standup",
            "14:00 - Project review",
        ],
    )


@router.get("/quick", response_model=QuickUpdate)
async def get_quick_update(
    auth: AuthContext = Depends(require_scopes("reachy:reports:read")),
):
    """Get a quick update for immediate announcement."""
    log_action(logger, "get_quick_update", user_id=auth.user_id)

    return QuickUpdate(
        message="All systems running smoothly.",
        priority="normal",
        category="status",
    )


@router.get("/notifications")
async def get_notifications(
    auth: AuthContext = Depends(require_scopes("reachy:notifications:read")),
):
    """Get pending notifications."""
    log_action(logger, "get_notifications", user_id=auth.user_id)

    # TODO: Implement notification fetching
    return {
        "count": 2,
        "notifications": [
            {"id": 1, "message": "New task assigned", "read": False},
            {"id": 2, "message": "Build completed", "read": False},
        ],
    }
