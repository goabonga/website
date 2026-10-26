# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""File upload service for handling user uploads."""

import hashlib
import logging
import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from auth.config import settings

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Upload error."""

    pass


class UploadService:
    """Service for handling file uploads."""

    def __init__(self) -> None:
        """Initialize the upload service."""
        self._upload_dir = Path(settings.upload_directory)
        self._max_size = settings.upload_max_size_mb * 1024 * 1024  # Convert to bytes
        self._allowed_types = set(settings.upload_allowed_types.split(","))

    def _ensure_directory(self, subdir: str = "") -> Path:
        """Ensure the upload directory exists.

        Args:
            subdir: Optional subdirectory within uploads.

        Returns:
            Path to the directory.
        """
        directory = self._upload_dir / subdir if subdir else self._upload_dir
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _get_file_extension(self, content_type: str) -> str:
        """Get file extension from content type.

        Args:
            content_type: MIME type of the file.

        Returns:
            File extension (without dot).
        """
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
        }
        return extensions.get(content_type, "bin")

    async def save_avatar(
        self,
        file: UploadFile,
        user_id: uuid.UUID,
    ) -> str:
        """Save a user avatar.

        Args:
            file: Uploaded file.
            user_id: User ID for organizing files.

        Returns:
            Relative path to the saved file.

        Raises:
            UploadError: If file validation fails.
        """
        # Validate content type
        if file.content_type not in self._allowed_types:
            raise UploadError(f"Invalid file type. Allowed types: {', '.join(self._allowed_types)}")

        # Read file content
        content = await file.read()

        # Validate file size
        if len(content) > self._max_size:
            raise UploadError(f"File too large. Maximum size: {settings.upload_max_size_mb}MB")

        # Generate unique filename using content hash
        content_hash = hashlib.sha256(content).hexdigest()[:16]
        extension = self._get_file_extension(file.content_type)
        filename = f"{content_hash}.{extension}"

        # Save to avatars subdirectory
        avatars_dir = self._ensure_directory("avatars")
        file_path = avatars_dir / filename

        # Write file
        with open(file_path, "wb") as f:
            f.write(content)

        # Return relative path for URL construction
        relative_path = f"avatars/{filename}"
        logger.info("Avatar saved for user %s: %s", user_id, relative_path)

        return relative_path

    def delete_avatar(self, relative_path: str) -> bool:
        """Delete an avatar file.

        Args:
            relative_path: Relative path to the file.

        Returns:
            True if deleted, False if not found.
        """
        file_path = self._upload_dir / relative_path
        if file_path.exists():
            os.remove(file_path)
            logger.info("Avatar deleted: %s", relative_path)
            return True
        return False

    def get_avatar_url(self, relative_path: str | None) -> str | None:
        """Get the full URL for an avatar.

        Args:
            relative_path: Relative path to the avatar.

        Returns:
            Full URL or None if no path.
        """
        if not relative_path:
            return None
        return f"/uploads/{relative_path}"

    def list_avatar_files(self) -> list[str]:
        """List all avatar filenames in the uploads directory.

        Returns:
            List of filenames (without path) in the avatars directory.
        """
        avatars_dir = self._upload_dir / "avatars"
        if not avatars_dir.exists():
            return []
        return [f.name for f in avatars_dir.iterdir() if f.is_file()]

    def delete_avatar_by_filename(self, filename: str) -> bool:
        """Delete an avatar file by filename.

        Args:
            filename: Filename (without path) to delete.

        Returns:
            True if deleted, False if not found.
        """
        file_path = self._upload_dir / "avatars" / filename
        if file_path.exists():
            os.remove(file_path)
            logger.info("Avatar deleted by filename: %s", filename)
            return True
        return False


# Singleton instance
upload_service = UploadService()
