# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.models.oauth2 — OAuth2 model __repr__ and DeviceCodeStatus."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from auth.db.models.oauth2 import (
    AccessToken,
    AuthorizationCode,
    DeviceCode,
    DeviceCodeStatus,
    OAuth2Client,
    PARRequest,
    RefreshToken,
)


class TestDeviceCodeStatus:
    def test_pending(self):
        assert DeviceCodeStatus.PENDING.value == "pending"

    def test_authorized(self):
        assert DeviceCodeStatus.AUTHORIZED.value == "authorized"

    def test_denied(self):
        assert DeviceCodeStatus.DENIED.value == "denied"

    def test_expired(self):
        assert DeviceCodeStatus.EXPIRED.value == "expired"

    def test_is_string_enum(self):
        assert isinstance(DeviceCodeStatus.PENDING, str)
        assert DeviceCodeStatus.PENDING == "pending"

    def test_from_value(self):
        assert DeviceCodeStatus("pending") == DeviceCodeStatus.PENDING
        assert DeviceCodeStatus("authorized") == DeviceCodeStatus.AUTHORIZED


class TestOAuth2ClientRepr:
    def test_repr(self):
        client = MagicMock(spec=OAuth2Client)
        client.client_id = "my-app"
        client.name = "My App"
        client.__repr__ = OAuth2Client.__repr__
        r = repr(client)
        assert "my-app" in r
        assert "My App" in r


class TestAuthorizationCodeRepr:
    def test_repr_unused(self):
        code = MagicMock(spec=AuthorizationCode)
        code.client_id = uuid.uuid4()
        code.used_at = None
        code.__repr__ = AuthorizationCode.__repr__
        r = repr(code)
        assert "used=False" in r

    def test_repr_used(self):
        code = MagicMock(spec=AuthorizationCode)
        code.client_id = uuid.uuid4()
        code.used_at = datetime.now(UTC)
        code.__repr__ = AuthorizationCode.__repr__
        r = repr(code)
        assert "used=True" in r


class TestAccessTokenRepr:
    def test_repr_not_revoked(self):
        token = MagicMock(spec=AccessToken)
        token.jti = "abc-123"
        token.revoked_at = None
        token.__repr__ = AccessToken.__repr__
        r = repr(token)
        assert "abc-123" in r
        assert "revoked=False" in r

    def test_repr_revoked(self):
        token = MagicMock(spec=AccessToken)
        token.jti = "def-456"
        token.revoked_at = datetime.now(UTC)
        token.__repr__ = AccessToken.__repr__
        r = repr(token)
        assert "revoked=True" in r


class TestRefreshTokenRepr:
    def test_repr_active(self):
        token = MagicMock(spec=RefreshToken)
        token.revoked_at = None
        token.used_at = None
        token.__repr__ = RefreshToken.__repr__
        r = repr(token)
        assert "revoked=False" in r
        assert "used=False" in r

    def test_repr_used_and_revoked(self):
        token = MagicMock(spec=RefreshToken)
        token.revoked_at = datetime.now(UTC)
        token.used_at = datetime.now(UTC)
        token.__repr__ = RefreshToken.__repr__
        r = repr(token)
        assert "revoked=True" in r
        assert "used=True" in r


class TestDeviceCodeRepr:
    def test_repr(self):
        dc = MagicMock(spec=DeviceCode)
        dc.user_code = "ABCD-1234"
        dc.status = "pending"
        dc.__repr__ = DeviceCode.__repr__
        r = repr(dc)
        assert "ABCD-1234" in r
        assert "pending" in r


class TestPARRequestRepr:
    def test_repr_unused(self):
        par = MagicMock(spec=PARRequest)
        par.request_uri = "urn:ietf:params:oauth:request_uri:abc"
        par.used_at = None
        par.__repr__ = PARRequest.__repr__
        r = repr(par)
        assert "urn:ietf:params:oauth:request_uri:abc" in r
        assert "used=False" in r

    def test_repr_used(self):
        par = MagicMock(spec=PARRequest)
        par.request_uri = "urn:test"
        par.used_at = datetime.now(UTC)
        par.__repr__ = PARRequest.__repr__
        r = repr(par)
        assert "used=True" in r
