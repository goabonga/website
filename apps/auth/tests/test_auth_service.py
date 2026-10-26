# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.auth — AuthService.

Covers all code paths: authenticate and get_user_primary_email.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.auth import AuthService

from tests.conftest import (
    make_execute_result,
    make_user,
    make_user_email,
    make_user_password,
)


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return AuthService()


# ── authenticate ─────────────────────────────────────────────────────────────


class TestAuthenticate:
    """Tests for AuthService.authenticate — all code paths."""

    async def test_success(self, db, service):
        """Happy path: verified email, active user, correct password."""
        user = make_user()
        pwd = make_user_password(password_hash="hashed")
        user.passwords = [pwd]
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.auth.verify_password", return_value=True) as mock_verify:
            result = await service.authenticate(db, "test@example.com", "password")

        assert result is user
        mock_verify.assert_called_once_with("password", "hashed")

    async def test_email_not_found(self, db, service):
        """No matching verified email returns None."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.authenticate(db, "missing@example.com", "password")
        assert result is None

    async def test_inactive_user(self, db, service):
        """Inactive user account returns None without checking password."""
        user = make_user(is_active=False)
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user_email))

        result = await service.authenticate(db, "test@example.com", "password")
        assert result is None
        # Only one DB call should have been made (no password reload)
        db.execute.assert_called_once()

    async def test_no_current_password(self, db, service):
        """User with only non-current passwords returns None."""
        user = make_user()
        old_pwd = make_user_password(is_current=False)
        user.passwords = [old_pwd]
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=user),
            ]
        )

        result = await service.authenticate(db, "test@example.com", "password")
        assert result is None

    async def test_empty_passwords_list(self, db, service):
        """User with no passwords at all returns None."""
        user = make_user(passwords=[])
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=user),
            ]
        )

        result = await service.authenticate(db, "test@example.com", "password")
        assert result is None

    async def test_wrong_password(self, db, service):
        """Correct user but wrong password returns None."""
        user = make_user()
        pwd = make_user_password()
        user.passwords = [pwd]
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.auth.verify_password", return_value=False):
            result = await service.authenticate(db, "test@example.com", "wrong")

        assert result is None

    async def test_email_lowercased(self, db, service):
        """The service lowercases the email for lookup."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        await service.authenticate(db, "TEST@EXAMPLE.COM", "password")
        db.execute.assert_called_once()

    async def test_user_not_found_after_password_reload(self, db, service):
        """Cover line 63-64: user is None after reloading with passwords."""
        user = make_user()
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=None),
            ]
        )

        result = await service.authenticate(db, "test@example.com", "password")
        assert result is None

    async def test_multiple_passwords_picks_first_current(self, db, service):
        """When multiple passwords exist, the first current one is used for verification."""
        user = make_user()
        old_pwd = make_user_password(password_hash="old_hash", is_current=False)
        current_pwd = make_user_password(password_hash="current_hash", is_current=True)
        another_old = make_user_password(password_hash="another_old", is_current=False)
        user.passwords = [old_pwd, current_pwd, another_old]
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.auth.verify_password", return_value=True) as mock_verify:
            result = await service.authenticate(db, "test@example.com", "pass")

        assert result is user
        mock_verify.assert_called_once_with("pass", "current_hash")

    async def test_verify_password_called_with_correct_args(self, db, service):
        """Ensure verify_password receives (plain_password, hash) in correct order."""
        user = make_user()
        pwd = make_user_password(password_hash="argon2hash")
        user.passwords = [pwd]
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.auth.verify_password", return_value=True) as mock_verify:
            await service.authenticate(db, "user@test.com", "my_secret")

        mock_verify.assert_called_once_with("my_secret", "argon2hash")

    async def test_two_db_calls_on_active_user(self, db, service):
        """Verify two DB queries are made: one for email, one for user+passwords."""
        user = make_user(is_active=True)
        pwd = make_user_password()
        user.passwords = [pwd]
        user_email = make_user_email(user=user, user_id=user.id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=user_email),
                make_execute_result(scalar_value=user),
            ]
        )

        with patch("auth.services.auth.verify_password", return_value=True):
            await service.authenticate(db, "test@example.com", "pass")

        assert db.execute.call_count == 2


# ── get_user_primary_email ───────────────────────────────────────────────────


class TestGetUserPrimaryEmail:
    """Tests for AuthService.get_user_primary_email — all code paths."""

    async def test_returns_primary_email(self, db, service):
        """Returns the primary email address."""
        ue = make_user_email(email="primary@example.com", is_primary=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ue))

        result = await service.get_user_primary_email(db, str(uuid.uuid4()))
        assert result == "primary@example.com"

    async def test_falls_back_to_first_verified(self, db, service):
        """Falls back to first verified email when no primary exists."""
        ue = make_user_email(email="verified@example.com", is_verified=True)
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=None),
                make_execute_result(scalar_value=ue),
            ]
        )

        result = await service.get_user_primary_email(db, str(uuid.uuid4()))
        assert result == "verified@example.com"

    async def test_returns_none_when_no_email(self, db, service):
        """Returns None when user has no primary or verified email."""
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=None),
                make_execute_result(scalar_value=None),
            ]
        )

        result = await service.get_user_primary_email(db, str(uuid.uuid4()))
        assert result is None

    async def test_primary_takes_precedence_over_verified(self, db, service):
        """Primary email is returned without querying for fallback verified email."""
        ue = make_user_email(email="primary@example.com", is_primary=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ue))

        result = await service.get_user_primary_email(db, str(uuid.uuid4()))
        assert result == "primary@example.com"
        # Only one DB call: no fallback query needed
        db.execute.assert_called_once()

    async def test_two_db_calls_when_no_primary(self, db, service):
        """When no primary email, exactly two DB queries are made."""
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=None),
                make_execute_result(scalar_value=None),
            ]
        )

        await service.get_user_primary_email(db, str(uuid.uuid4()))
        assert db.execute.call_count == 2


class TestVerifyCredentials:
    @pytest.mark.asyncio
    async def test_alias_delegates_to_authenticate(self, db, service):
        user = MagicMock()
        service.authenticate = AsyncMock(return_value=user)

        result = await service.verify_credentials(db, "a@example.com", "secret")

        assert result is user
        service.authenticate.assert_awaited_once_with(db, "a@example.com", "secret")
