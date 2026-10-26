# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MCP Downloads API endpoints.

Public API endpoints for listing and downloading MCP releases.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from knowledge.database import get_db
from knowledge.models import McpRelease, Platform, ReleaseStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/mcp", tags=["MCP Downloads"])


class AssetResponse(BaseModel):
    """Response model for a release asset."""

    platform: str
    filename: str
    download_url: str
    file_size: int | None
    sha256_checksum: str | None
    download_count: int

    model_config = ConfigDict(from_attributes=True)


class ReleaseResponse(BaseModel):
    """Response model for a release."""

    version: str
    release_notes: str | None
    status: str
    published_at: datetime | None
    assets: list[AssetResponse]

    model_config = ConfigDict(from_attributes=True)


class ReleaseSummaryResponse(BaseModel):
    """Response model for release list (without full assets)."""

    version: str
    status: str
    published_at: datetime | None
    platforms: list[str]

    model_config = ConfigDict(from_attributes=True)


@router.get("/releases", response_model=list[ReleaseSummaryResponse])
async def list_releases(
    db: AsyncSession = Depends(get_db),
    include_deprecated: bool = False,
) -> list[dict[str, Any]]:
    """List all published MCP releases.

    Returns releases sorted by version (newest first).
    """
    query = (
        select(McpRelease)
        .options(selectinload(McpRelease.assets))
        .where(McpRelease.status != ReleaseStatus.DRAFT)
        .order_by(desc(McpRelease.published_at))
    )

    if not include_deprecated:
        query = query.where(McpRelease.status == ReleaseStatus.PUBLISHED)

    result = await db.execute(query)
    releases = result.scalars().all()

    return [
        {
            "version": r.version,
            "status": r.status.value,
            "published_at": r.published_at,
            "platforms": [a.platform.value for a in r.assets],
        }
        for r in releases
    ]


@router.get("/releases/latest", response_model=ReleaseResponse)
async def get_latest_release(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the latest published MCP release."""
    result = await db.execute(
        select(McpRelease)
        .options(selectinload(McpRelease.assets))
        .where(McpRelease.status == ReleaseStatus.PUBLISHED)
        .order_by(desc(McpRelease.published_at))
        .limit(1)
    )
    release = result.scalar_one_or_none()

    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published releases found",
        )

    return {
        "version": release.version,
        "release_notes": release.release_notes,
        "status": release.status.value,
        "published_at": release.published_at,
        "assets": [
            {
                "platform": a.platform.value,
                "filename": a.filename,
                "download_url": a.download_url,
                "file_size": a.file_size,
                "sha256_checksum": a.sha256_checksum,
                "download_count": a.download_count,
            }
            for a in release.assets
        ],
    }


@router.get("/releases/{version}", response_model=ReleaseResponse)
async def get_release(
    version: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific MCP release by version."""
    # Remove 'v' prefix if present
    if version.startswith("v"):
        version = version[1:]

    result = await db.execute(
        select(McpRelease)
        .options(selectinload(McpRelease.assets))
        .where(McpRelease.version == version)
    )
    release = result.scalar_one_or_none()

    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{version}' not found",
        )

    return {
        "version": release.version,
        "release_notes": release.release_notes,
        "status": release.status.value,
        "published_at": release.published_at,
        "assets": [
            {
                "platform": a.platform.value,
                "filename": a.filename,
                "download_url": a.download_url,
                "file_size": a.file_size,
                "sha256_checksum": a.sha256_checksum,
                "download_count": a.download_count,
            }
            for a in release.assets
        ],
    }


@router.get("/download/{version}/{platform}")
async def download_release(
    version: str,
    platform: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Download a specific release for a platform.

    Redirects to the GitHub release asset URL and increments the download counter.
    """
    # Remove 'v' prefix if present
    if version.startswith("v"):
        version = version[1:]

    # Validate platform
    try:
        platform_enum = Platform(platform)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid platform '{platform}'. Valid platforms: {[p.value for p in Platform]}",
        )

    # Find the release
    result = await db.execute(
        select(McpRelease)
        .options(selectinload(McpRelease.assets))
        .where(McpRelease.version == version)
    )
    release = result.scalar_one_or_none()

    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{version}' not found",
        )

    # Find the asset for the platform
    asset = next((a for a in release.assets if a.platform == platform_enum), None)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No asset found for platform '{platform}' in release '{version}'",
        )

    # Increment download counter
    asset.download_count += 1
    await db.commit()

    logger.info(f"Download: {release.version}/{platform} (count: {asset.download_count})")

    # Redirect to GitHub download URL
    return RedirectResponse(url=asset.download_url, status_code=status.HTTP_302_FOUND)


@router.get("/download/latest/{platform}")
async def download_latest_release(
    platform: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Download the latest release for a platform.

    Redirects to the GitHub release asset URL and increments the download counter.
    """
    # Validate platform
    try:
        platform_enum = Platform(platform)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid platform '{platform}'. Valid platforms: {[p.value for p in Platform]}",
        )

    # Find the latest published release
    result = await db.execute(
        select(McpRelease)
        .options(selectinload(McpRelease.assets))
        .where(McpRelease.status == ReleaseStatus.PUBLISHED)
        .order_by(desc(McpRelease.published_at))
        .limit(1)
    )
    release = result.scalar_one_or_none()

    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published releases found",
        )

    # Find the asset for the platform
    asset = next((a for a in release.assets if a.platform == platform_enum), None)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No asset found for platform '{platform}' in latest release",
        )

    # Increment download counter
    asset.download_count += 1
    await db.commit()

    logger.info(f"Download latest: {release.version}/{platform} (count: {asset.download_count})")

    # Redirect to GitHub download URL
    return RedirectResponse(url=asset.download_url, status_code=status.HTTP_302_FOUND)
