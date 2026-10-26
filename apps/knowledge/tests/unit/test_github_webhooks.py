# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GitHub webhook functions: signature, platform detection, version parsing, release processing."""

from unittest.mock import AsyncMock, MagicMock

from knowledge.models.enums import Platform, ReleaseStatus
from knowledge.routes.github_webhooks import (
    GitHubAsset,
    GitHubRelease,
    detect_platform_from_filename,
    parse_version,
    process_release,
    verify_github_signature,
)

# ============================================================
# verify_github_signature (pure function)
# ============================================================


class TestVerifyGithubSignature:
    def test_valid_signature(self):
        payload = b'{"action": "published"}'
        secret = "my-secret"
        import hashlib
        import hmac

        expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        assert verify_github_signature(payload, expected, secret) is True

    def test_invalid_signature(self):
        payload = b'{"action": "published"}'
        assert verify_github_signature(payload, "sha256=badhex", "my-secret") is False

    def test_missing_sha256_prefix(self):
        payload = b'{"action": "published"}'
        assert verify_github_signature(payload, "md5=abc", "my-secret") is False

    def test_empty_signature(self):
        payload = b'{"action": "published"}'
        assert verify_github_signature(payload, "", "my-secret") is False


# ============================================================
# detect_platform_from_filename (pure function)
# ============================================================


class TestDetectPlatformFromFilename:
    def test_linux_x86_64(self):
        assert detect_platform_from_filename("knowledge-mcp-linux-x86_64") == Platform.LINUX_X86_64

    def test_linux_amd64(self):
        assert detect_platform_from_filename("knowledge-mcp-linux-amd64") == Platform.LINUX_X86_64

    def test_linux_arm64(self):
        assert detect_platform_from_filename("knowledge-mcp-linux-arm64") == Platform.LINUX_ARM64

    def test_linux_aarch64(self):
        assert detect_platform_from_filename("knowledge-mcp-linux-aarch64") == Platform.LINUX_ARM64

    def test_macos_x86_64(self):
        assert detect_platform_from_filename("knowledge-mcp-macos-x86_64") == Platform.MACOS_X86_64

    def test_darwin_x86_64(self):
        assert detect_platform_from_filename("knowledge-mcp-darwin-x86_64") == Platform.MACOS_X86_64

    def test_macos_arm64(self):
        assert detect_platform_from_filename("knowledge-mcp-macos-arm64") == Platform.MACOS_ARM64

    def test_darwin_arm64(self):
        assert detect_platform_from_filename("knowledge-mcp-darwin-arm64") == Platform.MACOS_ARM64

    def test_windows_exe(self):
        assert (
            detect_platform_from_filename("knowledge-mcp-windows-x86_64.exe")
            == Platform.WINDOWS_X86_64
        )

    def test_macos_no_arch(self):
        """macOS file without architecture info (branch 109->113)."""
        assert detect_platform_from_filename("knowledge-mcp-macos") is None

    def test_unknown(self):
        assert detect_platform_from_filename("README.md") is None

    def test_case_insensitive(self):
        assert detect_platform_from_filename("Knowledge-MCP-Linux-X86_64") == Platform.LINUX_X86_64


# ============================================================
# parse_version (pure function)
# ============================================================


class TestParseVersion:
    def test_with_v_prefix(self):
        assert parse_version("v1.2.3") == "1.2.3"

    def test_without_v_prefix(self):
        assert parse_version("1.2.3") == "1.2.3"

    def test_prerelease(self):
        assert parse_version("v2.0.0-beta.1") == "2.0.0-beta.1"


# ============================================================
# process_release (mock DB)
# ============================================================


class TestProcessRelease:
    async def test_new_release_created(self, mock_db, make_result):
        """New release is created when github_release_id not found."""
        # First execute: check existing release -> None
        # Second execute: check existing asset -> None (for each valid asset)
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(),  # no existing release
                make_result(),  # no existing asset for linux-x86_64
            ]
        )

        release = GitHubRelease(
            id=42,
            tag_name="v1.0.0",
            body="Release notes here",
            assets=[
                GitHubAsset(
                    id=1,
                    name="knowledge-mcp-linux-x86_64",
                    browser_download_url="https://example.com/download",
                    size=1024,
                ),
            ],
        )

        result = await process_release(mock_db, release)

        assert result is not None
        # db.add called for both the release and the asset
        assert mock_db.add.call_count == 2
        mock_db.flush.assert_called_once()

    async def test_existing_release_updated(self, mock_db, make_result):
        """Existing release is updated when github_release_id found."""
        existing_release = MagicMock()
        existing_release.id = 1
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing_release))

        release = GitHubRelease(
            id=42,
            tag_name="v2.0.0",
            body="Updated notes",
            assets=[],
        )

        result = await process_release(mock_db, release)

        assert result is existing_release
        assert existing_release.version == "2.0.0"
        assert existing_release.release_notes == "Updated notes"

    async def test_no_valid_assets(self, mock_db, make_result):
        """Release with no recognized platform assets still created."""
        mock_db.execute = AsyncMock(return_value=make_result())

        release = GitHubRelease(
            id=42,
            tag_name="v1.0.0",
            assets=[
                GitHubAsset(
                    id=1,
                    name="README.md",
                    browser_download_url="https://example.com/readme",
                    size=100,
                ),
            ],
        )

        result = await process_release(mock_db, release)
        assert result is not None

    async def test_draft_release_status(self, mock_db, make_result):
        """Draft release gets DRAFT status."""
        mock_db.execute = AsyncMock(return_value=make_result())

        release = GitHubRelease(
            id=42,
            tag_name="v1.0.0",
            draft=True,
            assets=[],
        )

        await process_release(mock_db, release)
        # The created McpRelease object is added via db.add
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.status == ReleaseStatus.DRAFT
