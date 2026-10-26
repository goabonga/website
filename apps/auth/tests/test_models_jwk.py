# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.models.jwk — JWK model __repr__."""

from unittest.mock import MagicMock

from auth.db.models.jwk import JWK


class TestJWKRepr:
    def test_repr_active(self):
        jwk = MagicMock(spec=JWK)
        jwk.kid = "key-abc-123"
        jwk.is_active = True
        jwk.__repr__ = JWK.__repr__
        r = repr(jwk)
        assert "key-abc-123" in r
        assert "active=True" in r

    def test_repr_inactive(self):
        jwk = MagicMock(spec=JWK)
        jwk.kid = "old-key"
        jwk.is_active = False
        jwk.__repr__ = JWK.__repr__
        r = repr(jwk)
        assert "old-key" in r
        assert "active=False" in r
