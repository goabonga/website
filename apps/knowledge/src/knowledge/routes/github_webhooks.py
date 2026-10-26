# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""GitHub webhook receiver for MCP releases.

Receives release events from GitHub and updates the mcp_releases table.
"""

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.config import get_settings
from knowledge.database import async_session_factory
from knowledge.models import McpRelease, McpReleaseAsset, Platform, ReleaseStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class GitHubAsset(BaseModel):
    """GitHub release asset."""

    id: int
    name: str
    browser_download_url: str
    size: int
    content_type: str | None = None


class GitHubRelease(BaseModel):
    """GitHub release data."""

    id: int
    tag_name: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    published_at: str | None = None
    assets: list[GitHubAsset] = []


class GitHubReleaseEvent(BaseModel):
    """GitHub release webhook event."""

    action: str
    release: GitHubRelease


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature.

    Args:
        payload: Raw request body.
        signature: Signature from X-Hub-Signature-256 header.
        secret: Webhook secret.

    Returns:
        True if signature is valid.
    """
    if not signature.startswith("sha256="):
        return False

    expected = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def detect_platform_from_filename(filename: str) -> Platform | None:
    """Detect platform from asset filename.

    Expected naming patterns:
    - knowledge-mcp-linux-x86_64
    - knowledge-mcp-linux-arm64
    - knowledge-mcp-macos-x86_64 / knowledge-mcp-darwin-x86_64
    - knowledge-mcp-macos-arm64 / knowledge-mcp-darwin-arm64
    - knowledge-mcp-windows-x86_64.exe

    Args:
        filename: Asset filename.

    Returns:
        Platform enum or None if not detected.
    """
    filename_lower = filename.lower()

    # Linux patterns
    if "linux" in filename_lower:
        if "x86_64" in filename_lower or "amd64" in filename_lower:
            return Platform.LINUX_X86_64
        if "arm64" in filename_lower or "aarch64" in filename_lower:
            return Platform.LINUX_ARM64

    # macOS patterns (also check for darwin)
    if "macos" in filename_lower or "darwin" in filename_lower:
        if "x86_64" in filename_lower or "amd64" in filename_lower:
            return Platform.MACOS_X86_64
        if "arm64" in filename_lower or "aarch64" in filename_lower:
            return Platform.MACOS_ARM64

    # Windows patterns
    if ("windows" in filename_lower or filename_lower.endswith(".exe")) and (
        "x86_64" in filename_lower or "amd64" in filename_lower or "win64" in filename_lower
    ):
        return Platform.WINDOWS_X86_64

    return None


def parse_version(tag_name: str) -> str:
    """Parse version from tag name.

    Removes 'v' prefix if present.

    Args:
        tag_name: Git tag name (e.g., "v1.0.0" or "1.0.0").

    Returns:
        Version string without 'v' prefix.
    """
    if tag_name.startswith("v"):
        return tag_name[1:]
    return tag_name


async def process_release(db: AsyncSession, release: GitHubRelease) -> McpRelease | None:
    """Process a GitHub release and create/update database records.

    Args:
        db: Database session.
        release: GitHub release data.

    Returns:
        Created or updated McpRelease, or None if no valid assets.
    """
    version = parse_version(release.tag_name)

    # Check if release already exists
    result = await db.execute(select(McpRelease).where(McpRelease.github_release_id == release.id))
    mcp_release = result.scalar_one_or_none()

    if mcp_release:
        # Update existing release
        mcp_release.version = version
        mcp_release.release_notes = release.body
        mcp_release.status = ReleaseStatus.PUBLISHED if not release.draft else ReleaseStatus.DRAFT
        if release.published_at:
            mcp_release.published_at = datetime.fromisoformat(
                release.published_at.replace("Z", "+00:00")
            )
        logger.info(f"Updated MCP release: {version}")
    else:
        # Create new release
        published_at = None
        if release.published_at:
            published_at = datetime.fromisoformat(release.published_at.replace("Z", "+00:00"))

        mcp_release = McpRelease(
            version=version,
            github_release_id=release.id,
            release_notes=release.body,
            status=ReleaseStatus.PUBLISHED if not release.draft else ReleaseStatus.DRAFT,
            published_at=published_at,
        )
        db.add(mcp_release)
        await db.flush()  # Get the ID
        logger.info(f"Created MCP release: {version}")

    # Process assets
    valid_assets = 0
    for asset in release.assets:
        platform = detect_platform_from_filename(asset.name)
        if not platform:
            logger.debug(f"Skipping asset with unknown platform: {asset.name}")
            continue

        # Check if asset already exists
        result = await db.execute(
            select(McpReleaseAsset).where(
                McpReleaseAsset.release_id == mcp_release.id,
                McpReleaseAsset.platform == platform,
            )
        )
        existing_asset: McpReleaseAsset | None = result.scalar_one_or_none()  # type: ignore[assignment]

        if existing_asset:
            # Update existing asset
            existing_asset.filename = asset.name
            existing_asset.download_url = asset.browser_download_url
            existing_asset.file_size = asset.size
            logger.debug(f"Updated asset for {platform.value}: {asset.name}")
        else:
            # Create new asset
            mcp_asset = McpReleaseAsset(
                release_id=mcp_release.id,
                platform=platform,
                filename=asset.name,
                download_url=asset.browser_download_url,
                file_size=asset.size,
            )
            db.add(mcp_asset)
            logger.debug(f"Created asset for {platform.value}: {asset.name}")

        valid_assets += 1

    if valid_assets == 0:
        logger.warning(f"No valid platform assets found for release {version}")

    return mcp_release


@router.post("/github/releases")
async def handle_github_release_webhook(request: Request) -> dict[str, Any]:
    """Receive GitHub release webhook events.

    Updates MCP releases database based on release events.
    """
    settings = get_settings()

    # Get raw payload for signature verification
    payload = await request.body()

    # Verify signature if secret is configured
    if settings.github_webhook_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature:
            logger.warning("Missing X-Hub-Signature-256 header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing signature",
            )

        if not verify_github_signature(payload, signature, settings.github_webhook_secret):
            logger.warning("Invalid GitHub webhook signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )

    # Check event type
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "release":
        logger.debug(f"Ignoring non-release event: {event_type}")
        return {"status": "ignored", "reason": f"Event type '{event_type}' not handled"}

    # Parse event
    try:
        event = GitHubReleaseEvent.model_validate_json(payload)
    except Exception as e:
        logger.error(f"Failed to parse GitHub webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )

    logger.info(
        f"Received GitHub release webhook: action={event.action}, tag={event.release.tag_name}"
    )

    # Only process published releases
    if event.action not in ["published", "edited", "released"]:
        logger.debug(f"Ignoring release action: {event.action}")
        return {"status": "ignored", "reason": f"Action '{event.action}' not handled"}

    async with async_session_factory() as db:
        try:
            mcp_release = await process_release(db, event.release)
            await db.commit()

            if mcp_release:
                return {
                    "status": "ok",
                    "release": {
                        "version": mcp_release.version,
                        "status": mcp_release.status.value,
                    },
                }
            else:
                return {"status": "ok", "message": "No valid assets found"}

        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to process GitHub webhook: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process webhook",
            )
