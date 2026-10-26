# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.models.user — User model __repr__ methods."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from auth.db.models.user import (
    MFABackupCode,
    MFAEmailCode,
    PasswordResetToken,
    Session,
    User,
    UserEmail,
    UserMFA,
    UserPassword,
    UserProfile,
    VerificationCode,
)


class TestUserRepr:
    def test_repr(self):
        user = MagicMock(spec=User)
        user.id = uuid.uuid4()
        user.is_active = True
        user.__repr__ = User.__repr__
        r = repr(user)
        assert str(user.id) in r
        assert "active=True" in r

    def test_repr_inactive(self):
        user = MagicMock(spec=User)
        user.id = uuid.uuid4()
        user.is_active = False
        user.__repr__ = User.__repr__
        r = repr(user)
        assert "active=False" in r


class TestUserEmailRepr:
    def test_repr(self):
        email = MagicMock(spec=UserEmail)
        email.email = "john@example.com"
        email.is_verified = True
        email.__repr__ = UserEmail.__repr__
        r = repr(email)
        assert "john@example.com" in r
        assert "verified=True" in r

    def test_repr_unverified(self):
        email = MagicMock(spec=UserEmail)
        email.email = "test@test.com"
        email.is_verified = False
        email.__repr__ = UserEmail.__repr__
        r = repr(email)
        assert "verified=False" in r


class TestUserPasswordRepr:
    def test_repr(self):
        pw = MagicMock(spec=UserPassword)
        pw.user_id = uuid.uuid4()
        pw.is_current = True
        pw.__repr__ = UserPassword.__repr__
        r = repr(pw)
        assert str(pw.user_id) in r
        assert "current=True" in r

    def test_repr_not_current(self):
        pw = MagicMock(spec=UserPassword)
        pw.user_id = uuid.uuid4()
        pw.is_current = False
        pw.__repr__ = UserPassword.__repr__
        r = repr(pw)
        assert "current=False" in r


class TestVerificationCodeRepr:
    def test_repr_unused(self):
        vc = MagicMock(spec=VerificationCode)
        vc.email = "test@example.com"
        vc.used_at = None
        vc.__repr__ = VerificationCode.__repr__
        r = repr(vc)
        assert "test@example.com" in r
        assert "used=False" in r

    def test_repr_used(self):
        vc = MagicMock(spec=VerificationCode)
        vc.email = "test@example.com"
        vc.used_at = datetime.now(UTC)
        vc.__repr__ = VerificationCode.__repr__
        r = repr(vc)
        assert "used=True" in r


class TestPasswordResetTokenRepr:
    def test_repr_unused(self):
        prt = MagicMock(spec=PasswordResetToken)
        prt.email = "user@example.com"
        prt.used_at = None
        prt.__repr__ = PasswordResetToken.__repr__
        r = repr(prt)
        assert "user@example.com" in r
        assert "used=False" in r

    def test_repr_used(self):
        prt = MagicMock(spec=PasswordResetToken)
        prt.email = "user@example.com"
        prt.used_at = datetime.now(UTC)
        prt.__repr__ = PasswordResetToken.__repr__
        r = repr(prt)
        assert "used=True" in r


class TestSessionRepr:
    def test_repr_active(self):
        sess = MagicMock(spec=Session)
        sess.user_id = uuid.uuid4()
        sess.revoked_at = None
        sess.__repr__ = Session.__repr__
        r = repr(sess)
        assert str(sess.user_id) in r
        assert "revoked=False" in r

    def test_repr_revoked(self):
        sess = MagicMock(spec=Session)
        sess.user_id = uuid.uuid4()
        sess.revoked_at = datetime.now(UTC)
        sess.__repr__ = Session.__repr__
        r = repr(sess)
        assert "revoked=True" in r


class TestUserMFARepr:
    def test_repr(self):
        mfa = MagicMock(spec=UserMFA)
        mfa.user_id = uuid.uuid4()
        mfa.totp_enabled = True
        mfa.__repr__ = UserMFA.__repr__
        r = repr(mfa)
        assert str(mfa.user_id) in r
        assert "totp_enabled=True" in r

    def test_repr_disabled(self):
        mfa = MagicMock(spec=UserMFA)
        mfa.user_id = uuid.uuid4()
        mfa.totp_enabled = False
        mfa.__repr__ = UserMFA.__repr__
        r = repr(mfa)
        assert "totp_enabled=False" in r


class TestMFABackupCodeRepr:
    def test_repr_unused(self):
        bc = MagicMock(spec=MFABackupCode)
        bc.used_at = None
        bc.__repr__ = MFABackupCode.__repr__
        r = repr(bc)
        assert "used=False" in r

    def test_repr_used(self):
        bc = MagicMock(spec=MFABackupCode)
        bc.used_at = datetime.now(UTC)
        bc.__repr__ = MFABackupCode.__repr__
        r = repr(bc)
        assert "used=True" in r


class TestMFAEmailCodeRepr:
    def test_repr_unused(self):
        mc = MagicMock(spec=MFAEmailCode)
        mc.email = "user@test.com"
        mc.used_at = None
        mc.__repr__ = MFAEmailCode.__repr__
        r = repr(mc)
        assert "user@test.com" in r
        assert "used=False" in r

    def test_repr_used(self):
        mc = MagicMock(spec=MFAEmailCode)
        mc.email = "user@test.com"
        mc.used_at = datetime.now(UTC)
        mc.__repr__ = MFAEmailCode.__repr__
        r = repr(mc)
        assert "used=True" in r


class TestUserProfileRepr:
    def test_repr(self):
        profile = MagicMock(spec=UserProfile)
        profile.user_id = uuid.uuid4()
        profile.name = "John Doe"
        profile.__repr__ = UserProfile.__repr__
        r = repr(profile)
        assert str(profile.user_id) in r
        assert "John Doe" in r
