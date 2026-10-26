# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.upload — UploadService."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from auth.services.upload import UploadError, UploadService


@pytest.fixture
def service():
    with patch("auth.services.upload.settings") as mock_settings:
        mock_settings.upload_directory = "/tmp/test-uploads"
        mock_settings.upload_max_size_mb = 5
        mock_settings.upload_allowed_types = "image/jpeg,image/png"
        svc = UploadService()
    return svc


# ── UploadError ───────────────────────────────────────────────────────────────


class TestUploadError:
    def test_is_exception(self):
        err = UploadError("bad file")
        assert isinstance(err, Exception)
        assert str(err) == "bad file"


# ── _get_file_extension ──────────────────────────────────────────────────────


class TestGetFileExtension:
    def test_jpeg(self, service):
        assert service._get_file_extension("image/jpeg") == "jpg"

    def test_png(self, service):
        assert service._get_file_extension("image/png") == "png"

    def test_gif(self, service):
        assert service._get_file_extension("image/gif") == "gif"

    def test_webp(self, service):
        assert service._get_file_extension("image/webp") == "webp"

    def test_unknown(self, service):
        assert service._get_file_extension("application/pdf") == "bin"


# ── _ensure_directory ─────────────────────────────────────────────────────────


class TestEnsureDirectory:
    def test_with_subdir(self, service):
        with patch.object(Path, "mkdir"):
            result = service._ensure_directory("avatars")
        assert str(result).endswith("avatars")

    def test_without_subdir(self, service):
        with patch.object(Path, "mkdir"):
            result = service._ensure_directory("")
        assert str(result) == "/tmp/test-uploads"


# ── save_avatar ──────────────────────────────────────────────────────────────


class TestSaveAvatar:
    @pytest.mark.asyncio
    async def test_success(self, service):
        file = AsyncMock()
        file.content_type = "image/jpeg"
        file.read = AsyncMock(return_value=b"fake image data")

        with (
            patch.object(Path, "mkdir"),
            patch("builtins.open", mock_open()),
        ):
            result = await service.save_avatar(file, uuid.uuid4())

        assert result.startswith("avatars/")
        assert result.endswith(".jpg")

    @pytest.mark.asyncio
    async def test_invalid_content_type(self, service):
        file = AsyncMock()
        file.content_type = "application/pdf"

        with pytest.raises(UploadError, match="Invalid file type"):
            await service.save_avatar(file, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_file_too_large(self, service):
        file = AsyncMock()
        file.content_type = "image/jpeg"
        # 6MB > 5MB max
        file.read = AsyncMock(return_value=b"x" * (6 * 1024 * 1024))

        with pytest.raises(UploadError, match="File too large"):
            await service.save_avatar(file, uuid.uuid4())


# ── delete_avatar ────────────────────────────────────────────────────────────


class TestDeleteAvatar:
    def test_exists(self, service):
        with (
            patch.object(Path, "exists", return_value=True),
            patch("auth.services.upload.os.remove") as mock_remove,
        ):
            result = service.delete_avatar("avatars/test.jpg")
        assert result is True
        mock_remove.assert_called_once()

    def test_not_exists(self, service):
        with patch.object(Path, "exists", return_value=False):
            result = service.delete_avatar("avatars/missing.jpg")
        assert result is False


# ── get_avatar_url ───────────────────────────────────────────────────────────


class TestGetAvatarUrl:
    def test_with_path(self, service):
        assert service.get_avatar_url("avatars/test.jpg") == "/uploads/avatars/test.jpg"

    def test_none_path(self, service):
        assert service.get_avatar_url(None) is None

    def test_empty_path(self, service):
        assert service.get_avatar_url("") is None


# ── list_avatar_files ────────────────────────────────────────────────────────


class TestListAvatarFiles:
    def test_with_files(self, service):
        mock_file1 = MagicMock()
        mock_file1.name = "a.jpg"
        mock_file1.is_file.return_value = True
        mock_file2 = MagicMock()
        mock_file2.name = "b.png"
        mock_file2.is_file.return_value = True

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "iterdir", return_value=[mock_file1, mock_file2]),
        ):
            result = service.list_avatar_files()
        assert result == ["a.jpg", "b.png"]

    def test_no_directory(self, service):
        with patch.object(Path, "exists", return_value=False):
            result = service.list_avatar_files()
        assert result == []

    def test_skips_directories(self, service):
        mock_dir = MagicMock()
        mock_dir.is_file.return_value = False
        mock_file = MagicMock()
        mock_file.name = "a.jpg"
        mock_file.is_file.return_value = True

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "iterdir", return_value=[mock_dir, mock_file]),
        ):
            result = service.list_avatar_files()
        assert result == ["a.jpg"]


# ── delete_avatar_by_filename ────────────────────────────────────────────────


class TestDeleteAvatarByFilename:
    def test_exists(self, service):
        with (
            patch.object(Path, "exists", return_value=True),
            patch("auth.services.upload.os.remove") as mock_remove,
        ):
            result = service.delete_avatar_by_filename("test.jpg")
        assert result is True
        mock_remove.assert_called_once()

    def test_not_exists(self, service):
        with patch.object(Path, "exists", return_value=False):
            result = service.delete_avatar_by_filename("missing.jpg")
        assert result is False
