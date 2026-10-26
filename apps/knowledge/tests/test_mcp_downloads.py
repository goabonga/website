# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for MCP download routes (knowledge/routes/mcp_downloads.py)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from knowledge.models.enums import Platform, ReleaseStatus
from tests.conftest import _make_result


def _make_mock_asset(**overrides):
    """Create a mock release asset."""
    asset = MagicMock()
    asset.platform = overrides.get("platform", Platform.LINUX_X86_64)
    asset.filename = overrides.get("filename", "knowledge-mcp-linux-x86_64")
    asset.download_url = overrides.get(
        "download_url", "https://github.com/download/v1.0.0/knowledge-mcp-linux-x86_64"
    )
    asset.file_size = overrides.get("file_size", 1000000)
    asset.sha256_checksum = overrides.get("sha256_checksum", "abc123")
    asset.download_count = overrides.get("download_count", 42)
    return asset


def _make_mock_release(**overrides):
    """Create a mock release."""
    release = MagicMock()
    release.version = overrides.get("version", "1.0.0")
    release.release_notes = overrides.get("release_notes", "Release notes")
    release.status = overrides.get("status", ReleaseStatus.PUBLISHED)
    release.published_at = overrides.get("published_at", datetime.now(UTC))
    release.assets = overrides.get("assets", [_make_mock_asset()])
    return release


# ============================================================
# list_releases
# ============================================================


@pytest.mark.asyncio
async def test_list_releases(client: AsyncClient, mock_db):
    """Test listing releases."""
    releases = [_make_mock_release(), _make_mock_release(version="0.9.0")]

    result = MagicMock()
    result.scalars.return_value.all.return_value = releases
    mock_db.execute = AsyncMock(return_value=result)

    response = await client.get("/api/v1/mcp/releases")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_list_releases_include_deprecated(client: AsyncClient, mock_db):
    """Test listing releases with deprecated included."""
    releases = [_make_mock_release()]
    result = MagicMock()
    result.scalars.return_value.all.return_value = releases
    mock_db.execute = AsyncMock(return_value=result)

    response = await client.get("/api/v1/mcp/releases?include_deprecated=true")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_releases_empty(client: AsyncClient, mock_db):
    """Test listing releases when none exist."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result)

    response = await client.get("/api/v1/mcp/releases")
    assert response.status_code == 200
    assert response.json() == []


# ============================================================
# get_latest_release
# ============================================================


@pytest.mark.asyncio
async def test_get_latest_release(client: AsyncClient, mock_db):
    """Test getting latest release."""
    release = _make_mock_release()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/releases/latest")
    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_get_latest_release_not_found(client: AsyncClient, mock_db):
    """Test getting latest release when none exist."""
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await client.get("/api/v1/mcp/releases/latest")
    assert response.status_code == 404


# ============================================================
# get_release (by version)
# ============================================================


@pytest.mark.asyncio
async def test_get_release_by_version(client: AsyncClient, mock_db):
    """Test getting a specific release by version."""
    release = _make_mock_release(version="1.2.3")
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/releases/1.2.3")
    assert response.status_code == 200
    assert response.json()["version"] == "1.2.3"


@pytest.mark.asyncio
async def test_get_release_with_v_prefix(client: AsyncClient, mock_db):
    """Test getting a release with 'v' prefix strips it."""
    release = _make_mock_release(version="1.2.3")
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/releases/v1.2.3")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_release_not_found(client: AsyncClient, mock_db):
    """Test getting non-existent release."""
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await client.get("/api/v1/mcp/releases/99.99.99")
    assert response.status_code == 404


# ============================================================
# download_release
# ============================================================


@pytest.mark.asyncio
async def test_download_release(client: AsyncClient, mock_db):
    """Test downloading a release."""
    asset = _make_mock_asset(platform=Platform.LINUX_X86_64, download_count=0)
    release = _make_mock_release(version="1.0.0", assets=[asset])
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/download/1.0.0/linux-x86_64", follow_redirects=False)
    assert response.status_code == 302
    assert asset.download_count == 1


@pytest.mark.asyncio
async def test_download_release_with_v_prefix(client: AsyncClient, mock_db):
    """Test downloading with 'v' prefix."""
    asset = _make_mock_asset(platform=Platform.LINUX_X86_64, download_count=0)
    release = _make_mock_release(version="1.0.0", assets=[asset])
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/download/v1.0.0/linux-x86_64", follow_redirects=False)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_download_release_invalid_platform(client: AsyncClient, mock_db):
    """Test downloading with invalid platform."""
    response = await client.get(
        "/api/v1/mcp/download/1.0.0/invalid-platform", follow_redirects=False
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_download_release_not_found(client: AsyncClient, mock_db):
    """Test downloading non-existent release."""
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await client.get(
        "/api/v1/mcp/download/99.99.99/linux-x86_64", follow_redirects=False
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_release_no_asset_for_platform(client: AsyncClient, mock_db):
    """Test downloading release with no asset for requested platform."""
    # Release has only macOS assets
    asset = _make_mock_asset(platform=Platform.MACOS_ARM64)
    release = _make_mock_release(version="1.0.0", assets=[asset])
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/download/1.0.0/linux-x86_64", follow_redirects=False)
    assert response.status_code == 404


# ============================================================
# download_latest_release
# ============================================================


@pytest.mark.asyncio
async def test_download_latest_release(client: AsyncClient, mock_db):
    """Test downloading the latest release."""
    asset = _make_mock_asset(platform=Platform.LINUX_X86_64, download_count=0)
    release = _make_mock_release(version="1.0.0", assets=[asset])
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/download/latest/linux-x86_64", follow_redirects=False)
    assert response.status_code == 302
    assert asset.download_count == 1


@pytest.mark.asyncio
async def test_download_latest_release_invalid_platform(client: AsyncClient, mock_db):
    """Test downloading latest with invalid platform."""
    response = await client.get(
        "/api/v1/mcp/download/latest/invalid-platform", follow_redirects=False
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_download_latest_release_no_release(client: AsyncClient, mock_db):
    """Test downloading latest when no releases exist."""
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await client.get("/api/v1/mcp/download/latest/linux-x86_64", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_latest_release_no_asset(client: AsyncClient, mock_db):
    """Test downloading latest when no asset for platform."""
    asset = _make_mock_asset(platform=Platform.MACOS_ARM64)
    release = _make_mock_release(version="1.0.0", assets=[asset])
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    response = await client.get("/api/v1/mcp/download/latest/linux-x86_64", follow_redirects=False)
    assert response.status_code == 404


# ============================================================
# download_latest_release — direct function tests
# (The HTTP route /download/{version}/{platform} is registered
#  before /download/latest/{platform}, so FastAPI matches the
#  former with version="latest". These tests call the function
#  directly to achieve coverage on lines 239-278.)
# ============================================================


@pytest.mark.asyncio
async def test_download_latest_release_fn_success(mock_db):
    """Call download_latest_release directly — happy path."""
    from knowledge.routes.mcp_downloads import download_latest_release

    asset = _make_mock_asset(platform=Platform.LINUX_X86_64, download_count=0)
    release = _make_mock_release(version="2.0.0", assets=[asset])
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    resp = await download_latest_release(platform="linux-x86_64", db=mock_db)
    assert resp.status_code == 302
    assert resp.headers["location"] == asset.download_url
    assert asset.download_count == 1
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_download_latest_release_fn_invalid_platform(mock_db):
    """Call download_latest_release directly — invalid platform returns 400."""
    from fastapi import HTTPException

    from knowledge.routes.mcp_downloads import download_latest_release

    with pytest.raises(HTTPException) as exc_info:
        await download_latest_release(platform="invalid-platform", db=mock_db)
    assert exc_info.value.status_code == 400
    assert "Invalid platform" in exc_info.value.detail


@pytest.mark.asyncio
async def test_download_latest_release_fn_no_release(mock_db):
    """Call download_latest_release directly — no published release returns 404."""
    from fastapi import HTTPException

    from knowledge.routes.mcp_downloads import download_latest_release

    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    with pytest.raises(HTTPException) as exc_info:
        await download_latest_release(platform="linux-x86_64", db=mock_db)
    assert exc_info.value.status_code == 404
    assert "No published releases" in exc_info.value.detail


@pytest.mark.asyncio
async def test_download_latest_release_fn_no_asset_for_platform(mock_db):
    """Call download_latest_release directly — no asset for requested platform returns 404."""
    from fastapi import HTTPException

    from knowledge.routes.mcp_downloads import download_latest_release

    asset = _make_mock_asset(platform=Platform.MACOS_ARM64)
    release = _make_mock_release(version="2.0.0", assets=[asset])
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=release))

    with pytest.raises(HTTPException) as exc_info:
        await download_latest_release(platform="linux-x86_64", db=mock_db)
    assert exc_info.value.status_code == 404
    assert "No asset found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_download_latest_is_not_resolved_as_a_version(client: AsyncClient, mock_db):
    """The 'latest' path must reach the latest-release handler, not the versioned one."""
    release = _make_mock_release()

    async def execute(statement):
        result = MagicMock()
        looked_up_by_version = "version_1" in statement.compile().params
        result.scalar_one_or_none.return_value = None if looked_up_by_version else release
        return result

    mock_db.execute = AsyncMock(side_effect=execute)

    response = await client.get("/api/v1/mcp/download/latest/linux-x86_64", follow_redirects=False)
    assert response.status_code == 302
