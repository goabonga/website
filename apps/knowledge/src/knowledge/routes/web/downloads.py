# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MCP Downloads web page."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from knowledge.database import get_db
from knowledge.models import McpRelease, ReleaseStatus
from knowledge.templating import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web"])
templates = create_templates()


@router.get("/mcp", response_class=HTMLResponse)
@router.get("/mcp/downloads", response_class=HTMLResponse)
async def mcp_downloads_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public MCP downloads page."""
    # Get all published releases
    result = await db.execute(
        select(McpRelease)
        .options(selectinload(McpRelease.assets))
        .where(McpRelease.status == ReleaseStatus.PUBLISHED)
        .order_by(desc(McpRelease.published_at))
    )
    releases = result.scalars().all()

    # Get latest release
    latest_release = releases[0] if releases else None

    return templates.TemplateResponse(
        request,
        "pages/mcp_downloads.html",
        {
            "releases": releases,
            "latest_release": latest_release,
        },
    )
