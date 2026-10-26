# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GitHub webhook routes (knowledge/routes/github_webhooks.py)."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge.database import get_db
from knowledge.main import app
from knowledge.models.enums import Platform, ReleaseStatus
from knowledge.routes.github_webhooks import (
    detect_platform_from_filename,
    parse_version,
    verify_github_signature,
)

# ============================================================
# Helpers
# ============================================================

WEBHOOK_SECRET = "test-github-secret"


@pytest.fixture
async def webhook_client(mock_db):
    """Test client for GitHub webhook (no auth needed)."""

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def _sign_payload(payload: bytes, secret: str) -> str:
    """Create GitHub webhook signature."""
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _make_release_event(
    action: str = "published",
    tag_name: str = "v1.0.0",
    draft: bool = False,
    body: str = "Release notes",
    assets: list[dict] | None = None,
    published_at: str = "2026-01-01T00:00:00Z",
) -> dict:
    """Create a GitHub release event."""
    if assets is None:
        assets = [
            {
                "id": 1,
                "name": "knowledge-mcp-linux-x86_64",
                "browser_download_url": "https://github.com/download/v1.0.0/knowledge-mcp-linux-x86_64",
                "size": 1000000,
            },
            {
                "id": 2,
                "name": "knowledge-mcp-macos-arm64",
                "browser_download_url": "https://github.com/download/v1.0.0/knowledge-mcp-macos-arm64",
                "size": 1100000,
            },
        ]
    return {
        "action": action,
        "release": {
            "id": 12345,
            "tag_name": tag_name,
            "name": f"Release {tag_name}",
            "body": body,
            "draft": draft,
            "prerelease": False,
            "published_at": published_at,
            "assets": assets,
        },
    }


# ============================================================
# Unit tests for helper functions
# ============================================================


def test_verify_github_signature_valid():
    """Test valid GitHub signature."""
    payload = b"test payload"
    sig = _sign_payload(payload, WEBHOOK_SECRET)
    assert verify_github_signature(payload, sig, WEBHOOK_SECRET) is True


def test_verify_github_signature_invalid():
    """Test invalid GitHub signature."""
    assert verify_github_signature(b"test", "sha256=invalid", WEBHOOK_SECRET) is False


def test_verify_github_signature_no_prefix():
    """Test signature without sha256= prefix."""
    assert verify_github_signature(b"test", "invalid_format", WEBHOOK_SECRET) is False


def test_parse_version():
    """Test version parsing."""
    assert parse_version("v1.0.0") == "1.0.0"
    assert parse_version("1.0.0") == "1.0.0"
    assert parse_version("v2.3.4-beta") == "2.3.4-beta"


def test_detect_platform_linux_x86():
    """Test Linux x86_64 detection."""
    assert detect_platform_from_filename("knowledge-mcp-linux-x86_64") == Platform.LINUX_X86_64
    assert detect_platform_from_filename("tool-linux-amd64") == Platform.LINUX_X86_64


def test_detect_platform_linux_arm():
    """Test Linux arm64 detection."""
    assert detect_platform_from_filename("knowledge-mcp-linux-arm64") == Platform.LINUX_ARM64
    assert detect_platform_from_filename("tool-linux-aarch64") == Platform.LINUX_ARM64


def test_detect_platform_macos_x86():
    """Test macOS x86_64 detection."""
    assert detect_platform_from_filename("knowledge-mcp-macos-x86_64") == Platform.MACOS_X86_64
    assert detect_platform_from_filename("tool-darwin-amd64") == Platform.MACOS_X86_64


def test_detect_platform_macos_arm():
    """Test macOS arm64 detection."""
    assert detect_platform_from_filename("knowledge-mcp-macos-arm64") == Platform.MACOS_ARM64
    assert detect_platform_from_filename("tool-darwin-aarch64") == Platform.MACOS_ARM64


def test_detect_platform_windows():
    """Test Windows x86_64 detection."""
    assert (
        detect_platform_from_filename("knowledge-mcp-windows-x86_64.exe") == Platform.WINDOWS_X86_64
    )
    assert detect_platform_from_filename("tool-win64-amd64.exe") == Platform.WINDOWS_X86_64


def test_detect_platform_unknown():
    """Test unknown platform returns None."""
    assert detect_platform_from_filename("README.md") is None
    assert detect_platform_from_filename("checksums.txt") is None


def test_detect_platform_linux_no_arch():
    """Test linux without architecture returns None."""
    assert detect_platform_from_filename("knowledge-mcp-linux") is None


# ============================================================
# Webhook endpoint tests
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
async def test_github_webhook_missing_signature(mock_get_settings, webhook_client: AsyncClient):
    """Test webhook with secret configured but missing signature."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = WEBHOOK_SECRET
    mock_get_settings.return_value = mock_settings

    event = _make_release_event()
    payload = json.dumps(event).encode()

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={"X-GitHub-Event": "release"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
async def test_github_webhook_invalid_signature(mock_get_settings, webhook_client: AsyncClient):
    """Test webhook with invalid signature."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = WEBHOOK_SECRET
    mock_get_settings.return_value = mock_settings

    event = _make_release_event()
    payload = json.dumps(event).encode()

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={
            "X-GitHub-Event": "release",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
async def test_github_webhook_non_release_event(mock_get_settings, webhook_client: AsyncClient):
    """Test webhook with non-release event type."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = ""
    mock_get_settings.return_value = mock_settings

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=b'{"action":"push"}',
        headers={"X-GitHub-Event": "push"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
async def test_github_webhook_invalid_payload(mock_get_settings, webhook_client: AsyncClient):
    """Test webhook with invalid payload."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = ""
    mock_get_settings.return_value = mock_settings

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=b"not valid json",
        headers={"X-GitHub-Event": "release"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
async def test_github_webhook_unhandled_action(mock_get_settings, webhook_client: AsyncClient):
    """Test webhook with unhandled action (e.g., 'deleted')."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = ""
    mock_get_settings.return_value = mock_settings

    event = _make_release_event(action="deleted")
    payload = json.dumps(event).encode()

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={"X-GitHub-Event": "release"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
@patch("knowledge.routes.github_webhooks.async_session_factory")
@patch("knowledge.routes.github_webhooks.process_release")
async def test_github_webhook_published_success(
    mock_process, mock_session_factory, mock_get_settings, webhook_client: AsyncClient
):
    """Test successful published release webhook."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = ""
    mock_get_settings.return_value = mock_settings

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session

    mock_release = MagicMock()
    mock_release.version = "1.0.0"
    mock_release.status = ReleaseStatus.PUBLISHED
    mock_process.return_value = mock_release

    event = _make_release_event(action="published")
    payload = json.dumps(event).encode()

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={"X-GitHub-Event": "release"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["release"]["version"] == "1.0.0"


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
@patch("knowledge.routes.github_webhooks.async_session_factory")
@patch("knowledge.routes.github_webhooks.process_release")
async def test_github_webhook_edited(
    mock_process, mock_session_factory, mock_get_settings, webhook_client: AsyncClient
):
    """Test edited release webhook."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = ""
    mock_get_settings.return_value = mock_settings

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session

    mock_release = MagicMock()
    mock_release.version = "1.0.0"
    mock_release.status = ReleaseStatus.PUBLISHED
    mock_process.return_value = mock_release

    event = _make_release_event(action="edited")
    payload = json.dumps(event).encode()

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={"X-GitHub-Event": "release"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
@patch("knowledge.routes.github_webhooks.async_session_factory")
@patch("knowledge.routes.github_webhooks.process_release")
async def test_github_webhook_no_valid_assets(
    mock_process, mock_session_factory, mock_get_settings, webhook_client: AsyncClient
):
    """Test webhook when no valid assets found."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = ""
    mock_get_settings.return_value = mock_settings

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session

    mock_process.return_value = None  # No valid assets

    event = _make_release_event(
        action="released",
        assets=[{"id": 1, "name": "README.md", "browser_download_url": "url", "size": 100}],
    )
    payload = json.dumps(event).encode()

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={"X-GitHub-Event": "release"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "No valid assets found"


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
@patch("knowledge.routes.github_webhooks.async_session_factory")
@patch("knowledge.routes.github_webhooks.process_release")
async def test_github_webhook_processing_error(
    mock_process, mock_session_factory, mock_get_settings, webhook_client: AsyncClient
):
    """Test webhook processing error (rollback)."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = ""
    mock_get_settings.return_value = mock_settings

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session

    mock_process.side_effect = Exception("DB error")

    event = _make_release_event(action="published")
    payload = json.dumps(event).encode()

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={"X-GitHub-Event": "release"},
    )
    assert response.status_code == 500


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.get_settings")
@patch("knowledge.routes.github_webhooks.async_session_factory")
@patch("knowledge.routes.github_webhooks.process_release")
async def test_github_webhook_with_valid_signature(
    mock_process, mock_session_factory, mock_get_settings, webhook_client: AsyncClient
):
    """Test webhook with valid signature."""
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = WEBHOOK_SECRET
    mock_get_settings.return_value = mock_settings

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session

    mock_release = MagicMock()
    mock_release.version = "1.0.0"
    mock_release.status = ReleaseStatus.PUBLISHED
    mock_process.return_value = mock_release

    event = _make_release_event(action="published")
    payload = json.dumps(event).encode()
    sig = _sign_payload(payload, WEBHOOK_SECRET)

    response = await webhook_client.post(
        "/webhooks/github/releases",
        content=payload,
        headers={
            "X-GitHub-Event": "release",
            "X-Hub-Signature-256": sig,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ============================================================
# process_release tests
# ============================================================


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.select")
async def test_process_release_new(mock_select):
    """Test processing a new release."""
    from knowledge.routes.github_webhooks import GitHubRelease, process_release
    from tests.conftest import _make_result

    mock_db = MagicMock()
    # First call: check for existing release -> None
    # Second call: check for existing asset -> None
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=None),  # No existing release
            _make_result(scalar_one_or_none=None),  # No existing asset
        ]
    )
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    release = GitHubRelease(
        id=12345,
        tag_name="v1.0.0",
        body="Notes",
        draft=False,
        published_at="2026-01-01T00:00:00Z",
        assets=[
            {
                "id": 1,
                "name": "knowledge-mcp-linux-x86_64",
                "browser_download_url": "https://example.com/dl",
                "size": 1000,
            }
        ],
    )

    result = await process_release(mock_db, release)
    assert result is not None
    mock_db.add.assert_called()


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.select")
async def test_process_release_existing(mock_select):
    """Test processing an existing release (update)."""
    from knowledge.routes.github_webhooks import GitHubRelease, process_release
    from tests.conftest import _make_result

    mock_db = MagicMock()

    existing_release = MagicMock()
    existing_release.id = uuid4()
    existing_release.version = "1.0.0"

    existing_asset = MagicMock()
    existing_asset.filename = "old-name"

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=existing_release),  # Existing release
            _make_result(scalar_one_or_none=existing_asset),  # Existing asset
        ]
    )
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    release = GitHubRelease(
        id=12345,
        tag_name="v1.0.0",
        body="Updated notes",
        draft=False,
        published_at="2026-01-01T00:00:00Z",
        assets=[
            {
                "id": 1,
                "name": "knowledge-mcp-linux-x86_64",
                "browser_download_url": "https://example.com/dl",
                "size": 2000,
            }
        ],
    )

    result = await process_release(mock_db, release)
    assert result is not None
    assert existing_release.version == "1.0.0"


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.select")
async def test_process_release_no_valid_assets(mock_select):
    """Test processing release with no valid platform assets."""
    from knowledge.routes.github_webhooks import GitHubRelease, process_release
    from tests.conftest import _make_result

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    release = GitHubRelease(
        id=12345,
        tag_name="v1.0.0",
        body="Notes",
        assets=[
            {
                "id": 1,
                "name": "README.md",
                "browser_download_url": "https://example.com/readme",
                "size": 500,
            }
        ],
    )

    result = await process_release(mock_db, release)
    assert result is not None  # Release is still created


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.select")
async def test_process_release_draft(mock_select):
    """Test processing a draft release."""
    from knowledge.routes.github_webhooks import GitHubRelease, process_release
    from tests.conftest import _make_result

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    release = GitHubRelease(
        id=12345,
        tag_name="v1.0.0",
        draft=True,
        published_at=None,
        assets=[],
    )

    result = await process_release(mock_db, release)
    assert result is not None


@pytest.mark.asyncio
@patch("knowledge.routes.github_webhooks.select")
async def test_process_release_existing_no_published_at(mock_select):
    """Test updating existing release without published_at."""
    from knowledge.routes.github_webhooks import GitHubRelease, process_release
    from tests.conftest import _make_result

    mock_db = MagicMock()

    existing_release = MagicMock()
    existing_release.id = uuid4()

    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=existing_release))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    release = GitHubRelease(
        id=12345,
        tag_name="v1.0.0",
        body="Notes",
        draft=False,
        published_at=None,
        assets=[],
    )

    result = await process_release(mock_db, release)
    assert result is not None
