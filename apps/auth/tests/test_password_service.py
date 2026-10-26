# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.password — PasswordService and helpers.

Covers all code paths: generate_reset_token, hash_token, create_reset_token,
verify_reset_token, reset_password, get_user_by_reset_token, change_password.
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.password import (
    PasswordService,
    generate_reset_token,
    hash_token,
)

from tests.conftest import (
    make_execute_result,
    make_password_reset_token,
    make_user,
    make_user_email,
    make_user_password,
)

# ── Helper functions ─────────────────────────────────────────────────────────


class TestGenerateResetToken:
    """Tests for generate_reset_token helper."""

    def test_length(self):
        """Token is 32 hex characters (16 random bytes)."""
        token = generate_reset_token()
        assert len(token) == 32

    def test_hex_format(self):
        """Token contains only valid hex characters."""
        token = generate_reset_token()
        int(token, 16)  # raises ValueError if not hex

    def test_randomness(self):
        """Successive tokens are different."""
        assert generate_reset_token() != generate_reset_token()


class TestHashTokenHelper:
    """Tests for hash_token helper."""

    def test_sha256(self):
        """Hashing produces correct SHA-256 hex digest."""
        token = "test"
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert hash_token(token) == expected

    def test_deterministic(self):
        """Same input always produces same hash."""
        assert hash_token("abc123") == hash_token("abc123")

    def test_different_inputs(self):
        """Different inputs produce different hashes."""
        assert hash_token("token_a") != hash_token("token_b")


# ── PasswordService ──────────────────────────────────────────────────────────


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return PasswordService()


class TestCreateResetToken:
    """Tests for PasswordService.create_reset_token."""

    async def test_success(self, db, service):
        """Happy path: verified email produces token and user_id."""
        ue = make_user_email(is_verified=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ue))

        result = await service.create_reset_token(db, "test@example.com")
        assert result is not None
        token, user_id = result
        assert len(token) == 32
        assert user_id == str(ue.user_id)
        db.add.assert_called_once()
        db.flush.assert_called_once()

    async def test_email_not_found(self, db, service):
        """Non-existent or unverified email returns None."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.create_reset_token(db, "missing@example.com")
        assert result is None
        db.add.assert_not_called()

    async def test_email_lowercased(self, db, service):
        """Email is lowercased before lookup."""
        ue = make_user_email(is_verified=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ue))

        result = await service.create_reset_token(db, "TEST@EXAMPLE.COM")
        assert result is not None

    async def test_token_is_hex_string(self, db, service):
        """Returned token is a valid hex string."""
        ue = make_user_email(is_verified=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ue))

        token, _ = await service.create_reset_token(db, "test@example.com")
        int(token, 16)  # should not raise


class TestVerifyResetToken:
    """Tests for PasswordService.verify_reset_token."""

    async def test_valid_token(self, db, service):
        """Valid token returns the PasswordResetToken object."""
        prt = make_password_reset_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=prt))

        result = await service.verify_reset_token(db, "valid_token")
        assert result is prt

    async def test_invalid_token(self, db, service):
        """Invalid/expired/used token returns None."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.verify_reset_token(db, "bad_token")
        assert result is None


class TestResetPassword:
    """Tests for PasswordService.reset_password."""

    async def test_success(self, db, service):
        """Happy path: valid token resets the password."""
        prt = make_password_reset_token()
        old_pwd = make_user_password(is_current=True)
        user = make_user(user_id=prt.user_id, passwords=[old_pwd])

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=prt),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.password.hash_password", return_value="new_hash"):
            result = await service.reset_password(db, "valid_token", "newpassword")

        assert result is True
        assert prt.used_at is not None
        assert old_pwd.is_current is False
        db.commit.assert_called_once()
        db.add.assert_called_once()

    async def test_invalid_token(self, db, service):
        """Invalid token returns False without modifying anything."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.reset_password(db, "bad_token", "newpassword")
        assert result is False
        db.commit.assert_not_called()

    async def test_user_not_found(self, db, service):
        """Valid token but missing user returns False."""
        prt = make_password_reset_token()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=prt),
                make_execute_result(scalar_value=None),
            ]
        )

        result = await service.reset_password(db, "token", "newpw")
        assert result is False
        db.commit.assert_not_called()

    async def test_resets_with_multiple_passwords(self, db, service):
        """Cover lines 154-156: loop marks only current passwords as not current."""
        prt = make_password_reset_token()
        old_pwd = make_user_password(is_current=False)
        current_pwd = make_user_password(is_current=True)
        user = make_user(user_id=prt.user_id, passwords=[old_pwd, current_pwd])

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=prt),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.password.hash_password", return_value="new_hash"):
            result = await service.reset_password(db, "valid_token", "newpassword")

        assert result is True
        assert current_pwd.is_current is False
        assert old_pwd.is_current is False

    async def test_token_marked_as_used(self, db, service):
        """Reset marks the token with a used_at timestamp."""
        prt = make_password_reset_token(used_at=None)
        user = make_user(user_id=prt.user_id, passwords=[])

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=prt),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.password.hash_password", return_value="new_hash"):
            await service.reset_password(db, "token", "newpw")

        assert prt.used_at is not None

    async def test_refresh_passwords_called(self, db, service):
        """reset_password calls db.refresh to load the passwords relationship."""
        prt = make_password_reset_token()
        user = make_user(user_id=prt.user_id, passwords=[])

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=prt),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.password.hash_password", return_value="new_hash"):
            await service.reset_password(db, "token", "newpw")

        db.refresh.assert_called_once_with(user, ["passwords"])


class TestGetUserByResetToken:
    """Tests for PasswordService.get_user_by_reset_token."""

    async def test_found(self, db, service):
        """Valid token returns the user."""
        prt = make_password_reset_token()
        user = make_user(user_id=prt.user_id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=prt),
                make_execute_result(scalar_value=user),
            ]
        )

        result = await service.get_user_by_reset_token(db, "token")
        assert result is user

    async def test_invalid_token(self, db, service):
        """Invalid token returns None without a second DB query."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_user_by_reset_token(db, "bad_token")
        assert result is None

    async def test_valid_token_but_user_gone(self, db, service):
        """Token is valid but user has been deleted returns None."""
        prt = make_password_reset_token()

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=prt),
                make_execute_result(scalar_value=None),
            ]
        )

        result = await service.get_user_by_reset_token(db, "token")
        assert result is None


class TestChangePassword:
    """Tests for PasswordService.change_password."""

    async def test_success(self, db, service):
        """Happy path: correct current password, new password is set."""
        current_pwd = make_user_password(password_hash="current_hash", is_current=True)
        user = make_user(passwords=[current_pwd])

        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        with (
            patch("auth.services.password.verify_password", return_value=True),
            patch("auth.services.password.hash_password", return_value="new_hash"),
        ):
            success, error = await service.change_password(db, str(user.id), "current_pw", "new_pw")

        assert success is True
        assert error is None
        assert current_pwd.is_current is False
        db.add.assert_called_once()
        db.flush.assert_called_once()

    async def test_user_not_found(self, db, service):
        """Non-existent user returns failure."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        success, error = await service.change_password(db, "missing_id", "old", "new")
        assert success is False
        assert error == "User not found"

    async def test_no_current_password(self, db, service):
        """User with no current password returns failure."""
        user = make_user(passwords=[make_user_password(is_current=False)])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        success, error = await service.change_password(db, str(user.id), "old", "new")
        assert success is False
        assert error == "No current password found"

    async def test_wrong_current_password(self, db, service):
        """Incorrect current password returns failure."""
        current_pwd = make_user_password(is_current=True)
        user = make_user(passwords=[current_pwd])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        with patch("auth.services.password.verify_password", return_value=False):
            success, error = await service.change_password(db, str(user.id), "wrong", "new")

        assert success is False
        assert error == "Current password is incorrect"

    async def test_empty_passwords_list(self, db, service):
        """User with empty passwords list returns no-current-password error."""
        user = make_user(passwords=[])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        success, error = await service.change_password(db, str(user.id), "old", "new")
        assert success is False
        assert error == "No current password found"

    async def test_refresh_passwords_called(self, db, service):
        """change_password calls db.refresh to load the passwords relationship."""
        current_pwd = make_user_password(password_hash="hash", is_current=True)
        user = make_user(passwords=[current_pwd])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        with (
            patch("auth.services.password.verify_password", return_value=True),
            patch("auth.services.password.hash_password", return_value="new_hash"),
        ):
            await service.change_password(db, str(user.id), "old", "new")

        db.refresh.assert_called_once_with(user, ["passwords"])

    async def test_verify_password_args_order(self, db, service):
        """Ensure verify_password is called with (plain, hash) argument order."""
        current_pwd = make_user_password(password_hash="stored_hash", is_current=True)
        user = make_user(passwords=[current_pwd])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        with (
            patch("auth.services.password.verify_password", return_value=True) as mock_verify,
            patch("auth.services.password.hash_password", return_value="new_hash"),
        ):
            await service.change_password(db, str(user.id), "my_current", "new")

        mock_verify.assert_called_once_with("my_current", "stored_hash")

    async def test_hash_password_called_with_new_password(self, db, service):
        """Ensure hash_password is called with the new password value."""
        current_pwd = make_user_password(password_hash="hash", is_current=True)
        user = make_user(passwords=[current_pwd])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        with (
            patch("auth.services.password.verify_password", return_value=True),
            patch("auth.services.password.hash_password", return_value="new_hash") as mock_hash,
        ):
            await service.change_password(db, str(user.id), "old", "my_new_pass")

        mock_hash.assert_called_once_with("my_new_pass")
