# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.schemas.pat — Personal Access Token schemas."""

from datetime import UTC, datetime

import pytest
from auth.api.schemas.pat import (
    AdminPATListResponse,
    AdminPATResponse,
    BulkRevokeRequest,
    CreatePATRequest,
    CreatePATResponse,
    PATExpirationPreset,
    PATListResponse,
    PATResponse,
    RevokePATRequest,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# PATExpirationPreset
# ---------------------------------------------------------------------------


class TestPATExpirationPreset:
    def test_all_values(self):
        assert PATExpirationPreset.DAYS_7 == "7_days"
        assert PATExpirationPreset.DAYS_30 == "30_days"
        assert PATExpirationPreset.DAYS_60 == "60_days"
        assert PATExpirationPreset.DAYS_90 == "90_days"
        assert PATExpirationPreset.DAYS_365 == "365_days"
        assert PATExpirationPreset.NO_EXPIRATION == "no_expiration"
        assert PATExpirationPreset.CUSTOM == "custom"

    def test_is_str_enum(self):
        assert isinstance(PATExpirationPreset.DAYS_7, str)


# ---------------------------------------------------------------------------
# CreatePATRequest
# ---------------------------------------------------------------------------


class TestCreatePATRequest:
    def test_minimal(self):
        r = CreatePATRequest(name="My Token", scopes=["users:read"])
        assert r.name == "My Token"
        assert r.description is None
        assert r.scopes == ["users:read"]
        assert r.expiration == PATExpirationPreset.DAYS_90
        assert r.custom_expiration_days is None
        assert r.tenant_id is None
        assert r.target_client_id is None

    def test_full(self):
        r = CreatePATRequest(
            name="Token",
            description="A test token",
            scopes=["users:read", "users:write"],
            expiration=PATExpirationPreset.CUSTOM,
            custom_expiration_days=180,
            tenant_id="t1",
            target_client_id="c1",
        )
        assert r.expiration == PATExpirationPreset.CUSTOM
        assert r.custom_expiration_days == 180

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            CreatePATRequest(name="", scopes=["users:read"])

    def test_name_too_long_raises(self):
        with pytest.raises(ValidationError):
            CreatePATRequest(name="x" * 256, scopes=["users:read"])

    def test_description_too_long_raises(self):
        with pytest.raises(ValidationError):
            CreatePATRequest(name="Token", scopes=["users:read"], description="x" * 1001)

    def test_empty_scopes_raises(self):
        with pytest.raises(ValidationError):
            CreatePATRequest(name="Token", scopes=[])

    def test_custom_expiration_too_low_raises(self):
        with pytest.raises(ValidationError):
            CreatePATRequest(
                name="Token",
                scopes=["users:read"],
                custom_expiration_days=0,
            )

    def test_custom_expiration_too_high_raises(self):
        with pytest.raises(ValidationError):
            CreatePATRequest(
                name="Token",
                scopes=["users:read"],
                custom_expiration_days=3651,
            )

    def test_custom_expiration_boundary_valid(self):
        r = CreatePATRequest(
            name="Token",
            scopes=["users:read"],
            custom_expiration_days=1,
        )
        assert r.custom_expiration_days == 1

        r2 = CreatePATRequest(
            name="Token",
            scopes=["users:read"],
            custom_expiration_days=3650,
        )
        assert r2.custom_expiration_days == 3650


# ---------------------------------------------------------------------------
# PATResponse
# ---------------------------------------------------------------------------

NOW = datetime.now(UTC)


class TestPATResponse:
    def test_valid(self):
        r = PATResponse(
            id="p1",
            name="My Token",
            description=None,
            scopes=["users:read"],
            token_suffix="abcd",
            created_at=NOW,
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            use_count=0,
            is_expired=False,
            is_revoked=False,
        )
        assert r.id == "p1"
        assert r.token_suffix == "abcd"
        assert r.tenant_id is None
        assert r.target_client_id is None

    def test_with_optional_fields(self):
        r = PATResponse(
            id="p1",
            name="My Token",
            description="desc",
            scopes=["users:read"],
            token_suffix="abcd",
            created_at=NOW,
            expires_at=NOW,
            last_used_at=NOW,
            last_used_ip="10.0.0.1",
            use_count=42,
            is_expired=True,
            is_revoked=True,
            tenant_id="t1",
            target_client_id="c1",
        )
        assert r.use_count == 42
        assert r.tenant_id == "t1"


# ---------------------------------------------------------------------------
# CreatePATResponse
# ---------------------------------------------------------------------------


class TestCreatePATResponse:
    def test_valid(self):
        pat = PATResponse(
            id="p1",
            name="Token",
            description=None,
            scopes=["users:read"],
            token_suffix="abcd",
            created_at=NOW,
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            use_count=0,
            is_expired=False,
            is_revoked=False,
        )
        r = CreatePATResponse(token="goab_fulltoken", pat=pat)
        assert r.token == "goab_fulltoken"
        assert r.pat.id == "p1"


# ---------------------------------------------------------------------------
# PATListResponse
# ---------------------------------------------------------------------------


class TestPATListResponse:
    def test_empty_list(self):
        r = PATListResponse(tokens=[], total=0, offset=0, limit=10)
        assert r.tokens == []
        assert r.total == 0

    def test_with_items(self):
        pat = PATResponse(
            id="p1",
            name="Token",
            description=None,
            scopes=["users:read"],
            token_suffix="abcd",
            created_at=NOW,
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            use_count=0,
            is_expired=False,
            is_revoked=False,
        )
        r = PATListResponse(tokens=[pat], total=1, offset=0, limit=10)
        assert len(r.tokens) == 1


# ---------------------------------------------------------------------------
# RevokePATRequest
# ---------------------------------------------------------------------------


class TestRevokePATRequest:
    def test_no_reason(self):
        r = RevokePATRequest()
        assert r.reason is None

    def test_with_reason(self):
        r = RevokePATRequest(reason="Compromised")
        assert r.reason == "Compromised"

    def test_reason_too_long_raises(self):
        with pytest.raises(ValidationError):
            RevokePATRequest(reason="x" * 501)


# ---------------------------------------------------------------------------
# BulkRevokeRequest
# ---------------------------------------------------------------------------


class TestBulkRevokeRequest:
    def test_valid(self):
        r = BulkRevokeRequest(user_id="u1")
        assert r.user_id == "u1"
        assert r.reason is None

    def test_with_reason(self):
        r = BulkRevokeRequest(user_id="u1", reason="Cleanup")
        assert r.reason == "Cleanup"

    def test_missing_user_id_raises(self):
        with pytest.raises(ValidationError):
            BulkRevokeRequest()

    def test_reason_too_long_raises(self):
        with pytest.raises(ValidationError):
            BulkRevokeRequest(user_id="u1", reason="x" * 501)


# ---------------------------------------------------------------------------
# AdminPATResponse
# ---------------------------------------------------------------------------


class TestAdminPATResponse:
    def test_valid(self):
        r = AdminPATResponse(
            id="p1",
            user_id="u1",
            user_email="user@example.com",
            name="Token",
            description=None,
            scopes=["users:read"],
            token_suffix="abcd",
            created_at=NOW,
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            use_count=0,
            is_expired=False,
            is_revoked=False,
        )
        assert r.user_id == "u1"
        assert r.user_email == "user@example.com"
        assert r.tenant_id is None

    def test_with_tenant(self):
        r = AdminPATResponse(
            id="p1",
            user_id="u1",
            user_email=None,
            name="Token",
            description=None,
            scopes=["users:read"],
            token_suffix="abcd",
            created_at=NOW,
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            use_count=0,
            is_expired=False,
            is_revoked=False,
            tenant_id="t1",
            target_client_id="c1",
        )
        assert r.tenant_id == "t1"


# ---------------------------------------------------------------------------
# AdminPATListResponse
# ---------------------------------------------------------------------------


class TestAdminPATListResponse:
    def test_empty(self):
        r = AdminPATListResponse(tokens=[], total=0, offset=0, limit=10)
        assert r.tokens == []
        assert r.total == 0
