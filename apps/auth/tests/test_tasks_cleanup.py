# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for database cleanup tasks."""

from unittest.mock import MagicMock, patch

from auth.tasks.cleanup import (
    cleanup_expired_authorization_codes,
    cleanup_expired_device_codes,
    cleanup_expired_mfa_email_codes,
    cleanup_expired_par_requests,
    cleanup_expired_password_reset_tokens,
    cleanup_expired_pats,
    cleanup_expired_sessions,
    cleanup_expired_tokens,
    cleanup_expired_verification_codes,
    cleanup_orphaned_avatars,
    cleanup_unverified_users,
)


def _make_mock_db(rowcount=5):
    """Create a mock DB session and get_sync_db context manager.

    Args:
        rowcount: The rowcount value to return from execute().

    Returns:
        Tuple of (mock_get_db, mock_db) where mock_get_db is the patched
        get_sync_db and mock_db is the session object yielded by the
        context manager.
    """
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.rowcount = rowcount
    mock_db.execute.return_value = mock_result

    mock_get_db = MagicMock()
    mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
    mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

    return mock_get_db, mock_db


class TestCleanupExpiredTokens:
    """Tests for cleanup_expired_tokens task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_both_token_types(self, mock_get_sync_db):
        """Should delete both refresh tokens and access tokens."""
        mock_db = MagicMock()

        refresh_result = MagicMock()
        refresh_result.rowcount = 3

        access_result = MagicMock()
        access_result.rowcount = 7

        mock_db.execute.side_effect = [refresh_result, access_result]

        mock_get_sync_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_sync_db.return_value.__exit__ = MagicMock(return_value=False)

        result = cleanup_expired_tokens()

        assert result == {
            "access_tokens_deleted": 7,
            "refresh_tokens_deleted": 3,
        }
        assert mock_db.execute.call_count == 2


class TestCleanupExpiredAuthorizationCodes:
    """Tests for cleanup_expired_authorization_codes task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_authorization_codes(self, mock_get_sync_db):
        """Should delete expired or used authorization codes."""
        mock_get_db, mock_db = _make_mock_db(rowcount=4)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_authorization_codes()

        assert result == {"authorization_codes_deleted": 4}
        mock_db.execute.assert_called_once()


class TestCleanupExpiredDeviceCodes:
    """Tests for cleanup_expired_device_codes task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_device_codes(self, mock_get_sync_db):
        """Should delete expired device codes."""
        mock_get_db, mock_db = _make_mock_db(rowcount=2)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_device_codes()

        assert result == {"device_codes_deleted": 2}
        mock_db.execute.assert_called_once()


class TestCleanupExpiredParRequests:
    """Tests for cleanup_expired_par_requests task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_par_requests(self, mock_get_sync_db):
        """Should delete expired PAR requests."""
        mock_get_db, mock_db = _make_mock_db(rowcount=6)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_par_requests()

        assert result == {"par_requests_deleted": 6}
        mock_db.execute.assert_called_once()


class TestCleanupExpiredVerificationCodes:
    """Tests for cleanup_expired_verification_codes task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_verification_codes(self, mock_get_sync_db):
        """Should delete expired verification codes."""
        mock_get_db, mock_db = _make_mock_db(rowcount=10)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_verification_codes()

        assert result == {"verification_codes_deleted": 10}
        mock_db.execute.assert_called_once()


class TestCleanupExpiredPasswordResetTokens:
    """Tests for cleanup_expired_password_reset_tokens task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_password_reset_tokens(self, mock_get_sync_db):
        """Should delete expired password reset tokens."""
        mock_get_db, mock_db = _make_mock_db(rowcount=1)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_password_reset_tokens()

        assert result == {"password_reset_tokens_deleted": 1}
        mock_db.execute.assert_called_once()


class TestCleanupExpiredMfaEmailCodes:
    """Tests for cleanup_expired_mfa_email_codes task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_mfa_email_codes(self, mock_get_sync_db):
        """Should delete expired MFA email codes."""
        mock_get_db, mock_db = _make_mock_db(rowcount=8)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_mfa_email_codes()

        assert result == {"mfa_email_codes_deleted": 8}
        mock_db.execute.assert_called_once()


class TestCleanupExpiredSessions:
    """Tests for cleanup_expired_sessions task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_sessions(self, mock_get_sync_db):
        """Should delete expired or revoked sessions."""
        mock_get_db, mock_db = _make_mock_db(rowcount=15)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_sessions()

        assert result == {"sessions_deleted": 15}
        mock_db.execute.assert_called_once()


class TestCleanupExpiredPats:
    """Tests for cleanup_expired_pats task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    def test_deletes_expired_pats(self, mock_get_sync_db):
        """Should delete expired and revoked personal access tokens past grace period."""
        mock_get_db, mock_db = _make_mock_db(rowcount=3)
        mock_get_sync_db.return_value.__enter__ = mock_get_db.return_value.__enter__
        mock_get_sync_db.return_value.__exit__ = mock_get_db.return_value.__exit__

        result = cleanup_expired_pats()

        assert result == {"pats_deleted": 3}
        mock_db.execute.assert_called_once()


class TestCleanupOrphanedAvatars:
    """Tests for cleanup_orphaned_avatars task."""

    @patch("auth.tasks.cleanup.settings")
    def test_disabled_when_setting_is_off(self, mock_settings):
        """Should skip cleanup when orphan_avatar_cleanup_enabled is False."""
        mock_settings.orphan_avatar_cleanup_enabled = False

        result = cleanup_orphaned_avatars()

        assert result == {"avatars_deleted": 0, "skipped": True}

    @patch("auth.tasks.cleanup.upload_service")
    @patch("auth.tasks.cleanup.settings")
    def test_no_files_on_disk(self, mock_settings, mock_upload_service):
        """Should return zero when no avatar files exist on disk."""
        mock_settings.orphan_avatar_cleanup_enabled = True
        mock_upload_service.list_avatar_files.return_value = []

        result = cleanup_orphaned_avatars()

        assert result == {"avatars_deleted": 0}
        mock_upload_service.list_avatar_files.assert_called_once()

    @patch("auth.tasks.cleanup.get_sync_db")
    @patch("auth.tasks.cleanup.upload_service")
    @patch("auth.tasks.cleanup.settings")
    def test_deletes_orphaned_avatars(self, mock_settings, mock_upload_service, mock_get_sync_db):
        """Should delete avatar files not referenced in the database."""
        mock_settings.orphan_avatar_cleanup_enabled = True
        mock_upload_service.list_avatar_files.return_value = [
            "avatar1.jpg",
            "avatar2.jpg",
            "avatar3.jpg",
        ]
        mock_upload_service.delete_avatar_by_filename.return_value = True

        # Mock DB to return one referenced avatar
        mock_db = MagicMock()
        mock_db.execute.return_value = [
            ("/uploads/avatars/avatar1.jpg",),
        ]
        mock_get_sync_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_sync_db.return_value.__exit__ = MagicMock(return_value=False)

        result = cleanup_orphaned_avatars()

        assert result == {"avatars_deleted": 2}
        assert mock_upload_service.delete_avatar_by_filename.call_count == 2


class TestCleanupUnverifiedUsers:
    """Tests for cleanup_unverified_users task."""

    @patch("auth.tasks.cleanup.get_sync_db")
    @patch("auth.tasks.cleanup.settings")
    def test_no_unverified_users(self, mock_settings, mock_get_sync_db):
        """Should return zero counts when no unverified users are found."""
        mock_settings.unverified_user_expiry_days = 7

        mock_db = MagicMock()
        # The select query returns an empty iterable
        mock_db.execute.return_value = []
        mock_get_sync_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_sync_db.return_value.__exit__ = MagicMock(return_value=False)

        result = cleanup_unverified_users()

        assert result == {"users_deleted": 0, "avatars_deleted": 0}

    @patch("auth.tasks.cleanup.upload_service")
    @patch("auth.tasks.cleanup.get_sync_db")
    @patch("auth.tasks.cleanup.settings")
    def test_deletes_users_with_avatars(self, mock_settings, mock_get_sync_db, mock_upload_service):
        """Should delete unverified users and their avatar files."""
        mock_settings.unverified_user_expiry_days = 7
        mock_upload_service.delete_avatar_by_filename.return_value = True

        mock_user1 = MagicMock()
        mock_user1.created_at = "2024-01-01T00:00:00Z"

        mock_email1 = MagicMock()
        mock_email1.email = "user1@example.com"

        mock_profile1 = MagicMock()
        mock_profile1.picture_url = "/uploads/avatars/user1_avatar.jpg"

        mock_user2 = MagicMock()
        mock_user2.created_at = "2024-01-02T00:00:00Z"

        mock_email2 = MagicMock()
        mock_email2.email = "user2@example.com"

        mock_profile2 = None  # No profile for this user

        mock_db = MagicMock()
        mock_db.execute.return_value = [
            (mock_user1, mock_email1, mock_profile1),
            (mock_user2, mock_email2, mock_profile2),
        ]
        mock_get_sync_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_sync_db.return_value.__exit__ = MagicMock(return_value=False)

        result = cleanup_unverified_users()

        assert result == {"users_deleted": 2, "avatars_deleted": 1}
        assert mock_db.delete.call_count == 2
        mock_db.commit.assert_called_once()
        mock_upload_service.delete_avatar_by_filename.assert_called_once_with("user1_avatar.jpg")


class TestCleanupOrphanedAvatarsEdgeCases:
    """Branch coverage for non-avatar picture URLs and failed deletions."""

    @patch("auth.tasks.cleanup.get_sync_db")
    @patch("auth.tasks.cleanup.upload_service")
    @patch("auth.tasks.cleanup.settings")
    def test_non_avatar_picture_urls_are_ignored(
        self, mock_settings, mock_upload_service, mock_get_sync_db
    ):
        """External picture URLs (no /avatars/ segment) never shield a file from cleanup."""
        mock_settings.orphan_avatar_cleanup_enabled = True
        mock_upload_service.list_avatar_files.return_value = ["avatar1.jpg"]
        mock_upload_service.delete_avatar_by_filename.return_value = True

        mock_db = MagicMock()
        mock_db.execute.return_value = [("https://gravatar.com/avatar1.jpg",)]
        mock_get_sync_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_sync_db.return_value.__exit__ = MagicMock(return_value=False)

        assert cleanup_orphaned_avatars() == {"avatars_deleted": 1}

    @patch("auth.tasks.cleanup.get_sync_db")
    @patch("auth.tasks.cleanup.upload_service")
    @patch("auth.tasks.cleanup.settings")
    def test_failed_deletion_is_not_counted(
        self, mock_settings, mock_upload_service, mock_get_sync_db
    ):
        """A file the upload service refuses to delete does not increment the counter."""
        mock_settings.orphan_avatar_cleanup_enabled = True
        mock_upload_service.list_avatar_files.return_value = ["avatar1.jpg"]
        mock_upload_service.delete_avatar_by_filename.return_value = False

        mock_db = MagicMock()
        mock_db.execute.return_value = []
        mock_get_sync_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_sync_db.return_value.__exit__ = MagicMock(return_value=False)

        assert cleanup_orphaned_avatars() == {"avatars_deleted": 0}


class TestCleanupUnverifiedUsersAvatarDeletionFails:
    @patch("auth.tasks.cleanup.upload_service")
    @patch("auth.tasks.cleanup.get_sync_db")
    @patch("auth.tasks.cleanup.settings")
    def test_avatar_not_counted_when_delete_fails(
        self, mock_settings, mock_get_sync_db, mock_upload_service
    ):
        """The user is still deleted even when its avatar file cannot be removed."""
        mock_settings.unverified_user_expiry_days = 7
        mock_upload_service.delete_avatar_by_filename.return_value = False

        user = MagicMock()
        user.created_at = "2024-01-01T00:00:00Z"
        email = MagicMock()
        email.email = "user@example.com"
        profile = MagicMock()
        profile.picture_url = "/uploads/avatars/user_avatar.jpg"

        mock_db = MagicMock()
        mock_db.execute.return_value = [(user, email, profile)]
        mock_get_sync_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_sync_db.return_value.__exit__ = MagicMock(return_value=False)

        assert cleanup_unverified_users() == {"users_deleted": 1, "avatars_deleted": 0}
        mock_db.delete.assert_called_once_with(user)
