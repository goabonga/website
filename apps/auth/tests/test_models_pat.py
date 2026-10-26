# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.models.pat — PersonalAccessToken model properties."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from auth.db.models.pat import PATExpirationPreset, PersonalAccessToken


class TestPATExpirationPreset:
    def test_values(self):
        assert PATExpirationPreset.DAYS_7 == "7_days"
        assert PATExpirationPreset.DAYS_30 == "30_days"
        assert PATExpirationPreset.DAYS_60 == "60_days"
        assert PATExpirationPreset.DAYS_90 == "90_days"
        assert PATExpirationPreset.DAYS_365 == "365_days"
        assert PATExpirationPreset.NO_EXPIRATION == "no_expiration"
        assert PATExpirationPreset.CUSTOM == "custom"


def _make_pat(expires_at=None, revoked_at=None):
    """Create a mock PAT that uses the real is_expired / is_valid properties."""
    pat = MagicMock(spec=PersonalAccessToken)
    pat.expires_at = expires_at
    pat.revoked_at = revoked_at
    # Wire up the real properties via the class
    type(pat).is_expired = PersonalAccessToken.is_expired
    type(pat).is_valid = PersonalAccessToken.is_valid
    return pat


class TestIsExpired:
    def test_no_expiration(self):
        pat = _make_pat(expires_at=None)
        assert pat.is_expired is False

    def test_future_expiration(self):
        pat = _make_pat(expires_at=datetime.now(UTC) + timedelta(days=1))
        assert pat.is_expired is False

    def test_past_expiration(self):
        pat = _make_pat(expires_at=datetime.now(UTC) - timedelta(days=1))
        assert pat.is_expired is True


class TestIsValid:
    def test_valid_not_expired_not_revoked(self):
        pat = _make_pat(expires_at=None, revoked_at=None)
        assert pat.is_valid is True

    def test_invalid_expired(self):
        pat = _make_pat(
            expires_at=datetime.now(UTC) - timedelta(days=1),
            revoked_at=None,
        )
        assert pat.is_valid is False

    def test_invalid_revoked(self):
        pat = _make_pat(expires_at=None, revoked_at=datetime.now(UTC))
        assert pat.is_valid is False

    def test_invalid_both(self):
        pat = _make_pat(
            expires_at=datetime.now(UTC) - timedelta(days=1),
            revoked_at=datetime.now(UTC),
        )
        assert pat.is_valid is False


class TestRepr:
    def test_repr(self):
        pat = MagicMock(spec=PersonalAccessToken)
        pat.name = "My Token"
        pat.user_id = uuid.uuid4()
        pat.revoked_at = None
        pat.__repr__ = PersonalAccessToken.__repr__
        result = repr(pat)
        assert "My Token" in result
        assert "revoked=False" in result

    def test_repr_revoked(self):
        pat = MagicMock(spec=PersonalAccessToken)
        pat.name = "Revoked"
        pat.user_id = uuid.uuid4()
        pat.revoked_at = datetime.now(UTC)
        pat.__repr__ = PersonalAccessToken.__repr__
        result = repr(pat)
        assert "revoked=True" in result
