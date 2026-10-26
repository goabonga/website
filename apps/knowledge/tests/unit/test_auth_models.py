# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/auth/models.py — 100% coverage with only mocks."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from knowledge.auth.models import User, WebAuthContext

# =====================================================================
# User model tests
# =====================================================================


class TestUser:
    """Tests for the User pydantic model."""

    def _make_user(self, scopes=None, **kwargs):
        defaults = {
            "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "email": "user@example.com",
            "name": "Test User",
            "nickname": None,
            "scopes": scopes or [],
        }
        defaults.update(kwargs)
        return User(**defaults)

    # ------------------------------------------------------------------
    # display_name property
    # ------------------------------------------------------------------
    def test_display_name_with_nickname(self):
        u = self._make_user(nickname="nick")
        assert u.display_name == "nick"

    def test_display_name_fallback_to_name(self):
        u = self._make_user(name="Full Name", nickname=None)
        assert u.display_name == "Full Name"

    def test_display_name_none_when_both_missing(self):
        u = self._make_user(name=None, nickname=None)
        assert u.display_name is None

    # ------------------------------------------------------------------
    # from_jwt_claims
    # ------------------------------------------------------------------
    def test_from_jwt_claims_basic(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "email": "u@e.com",
            "name": "J",
            "scope": "read write",
        }
        u = User.from_jwt_claims(claims)
        assert u.id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        assert u.email == "u@e.com"
        assert u.name == "J"
        assert u.scopes == ["read", "write"]

    def test_from_jwt_claims_scope_as_list(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "scope": ["a", "b"],
        }
        u = User.from_jwt_claims(claims)
        assert u.scopes == ["a", "b"]

    def test_from_jwt_claims_empty_scope_string(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "scope": "",
        }
        u = User.from_jwt_claims(claims)
        assert u.scopes == []

    def test_from_jwt_claims_no_scope(self):
        claims = {"sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
        u = User.from_jwt_claims(claims)
        assert u.scopes == []

    def test_from_jwt_claims_name_fallback_displayName(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "displayName": "DN",
        }
        u = User.from_jwt_claims(claims)
        assert u.name == "DN"

    def test_from_jwt_claims_name_fallback_display_name(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "display_name": "D_N",
        }
        u = User.from_jwt_claims(claims)
        assert u.name == "D_N"

    def test_from_jwt_claims_name_fallback_given_name(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "given_name": "GN",
        }
        u = User.from_jwt_claims(claims)
        assert u.name == "GN"

    def test_from_jwt_claims_nickname_preferred_username(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "preferred_username": "pref",
        }
        u = User.from_jwt_claims(claims)
        assert u.nickname == "pref"

    def test_from_jwt_claims_nickname_field(self):
        claims = {
            "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "nickname": "nick",
            "preferred_username": "pref",
        }
        u = User.from_jwt_claims(claims)
        assert u.nickname == "nick"

    # ------------------------------------------------------------------
    # has_scope
    # ------------------------------------------------------------------
    def test_has_scope_wildcard_star(self):
        u = self._make_user(scopes=["*"])
        assert u.has_scope("anything") is True

    def test_has_scope_exact_match(self):
        u = self._make_user(scopes=["api:read"])
        assert u.has_scope("api:read") is True

    def test_has_scope_no_match(self):
        u = self._make_user(scopes=["api:read"])
        assert u.has_scope("api:write") is False

    def test_has_scope_wildcard_prefix(self):
        u = self._make_user(scopes=["knowledge:*"])
        assert u.has_scope("knowledge:read") is True
        assert u.has_scope("knowledge:write") is True

    def test_has_scope_wildcard_prefix_no_match(self):
        u = self._make_user(scopes=["knowledge:*"])
        assert u.has_scope("billing:read") is False

    def test_has_scope_simple_scope_no_colon(self):
        u = self._make_user(scopes=["admin"])
        assert u.has_scope("admin") is True
        assert u.has_scope("user") is False

    def test_has_scope_no_scopes(self):
        u = self._make_user(scopes=[])
        assert u.has_scope("anything") is False

    def test_has_scope_wildcard_prefix_not_matching_different_prefix(self):
        u = self._make_user(scopes=["api:*"])
        assert u.has_scope("knowledge:read") is False

    # ------------------------------------------------------------------
    # require_scope
    # ------------------------------------------------------------------
    def test_require_scope_passes(self):
        u = self._make_user(scopes=["api:read"])
        # Should not raise
        u.require_scope("api:read")

    def test_require_scope_fails(self):
        u = self._make_user(scopes=["api:read"])
        with pytest.raises(HTTPException) as exc_info:
            u.require_scope("api:write")
        assert exc_info.value.status_code == 403
        assert "Missing required scope" in exc_info.value.detail

    # ------------------------------------------------------------------
    # can_read / can_write / can_delete
    # ------------------------------------------------------------------
    def test_can_read(self):
        u = self._make_user(scopes=["knowledge:read"])
        assert u.can_read("knowledge") is True
        assert u.can_read("billing") is False

    def test_can_write(self):
        u = self._make_user(scopes=["knowledge:write"])
        assert u.can_write("knowledge") is True
        assert u.can_write("billing") is False

    def test_can_delete_with_delete_scope(self):
        u = self._make_user(scopes=["knowledge:delete"])
        assert u.can_delete("knowledge") is True

    def test_can_delete_with_write_scope(self):
        u = self._make_user(scopes=["knowledge:write"])
        assert u.can_delete("knowledge") is True

    def test_can_delete_fails(self):
        u = self._make_user(scopes=["knowledge:read"])
        assert u.can_delete("knowledge") is False


# =====================================================================
# WebAuthContext tests
# =====================================================================


class TestWebAuthContext:
    """Tests for the WebAuthContext model."""

    def _make_user(self, uid=None, scopes=None):
        return User(
            id=uid or UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            email="u@e.com",
            name="Test",
            scopes=scopes or [],
        )

    def _make_ctx(self, user=None, tenant=None, tenant_member=None):
        return WebAuthContext(
            user=user or self._make_user(),
            tenant=tenant,
            tenant_member=tenant_member,
        )

    # ------------------------------------------------------------------
    # user_id
    # ------------------------------------------------------------------
    def test_user_id(self):
        uid = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        ctx = self._make_ctx(user=self._make_user(uid=uid))
        assert ctx.user_id == uid

    # ------------------------------------------------------------------
    # tenant_id
    # ------------------------------------------------------------------
    def test_tenant_id_with_tenant(self):
        tenant = MagicMock()
        tenant.id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        ctx = self._make_ctx(tenant=tenant)
        assert ctx.tenant_id == UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    def test_tenant_id_no_tenant_raises(self):
        ctx = self._make_ctx(tenant=None)
        with pytest.raises(HTTPException) as exc_info:
            _ = ctx.tenant_id
        assert exc_info.value.status_code == 403
        assert "No active tenant" in exc_info.value.detail

    # ------------------------------------------------------------------
    # scopes
    # ------------------------------------------------------------------
    def test_scopes(self):
        ctx = self._make_ctx(user=self._make_user(scopes=["a", "b"]))
        assert ctx.scopes == ["a", "b"]

    # ------------------------------------------------------------------
    # has_scope
    # ------------------------------------------------------------------
    def test_has_scope_delegates(self):
        ctx = self._make_ctx(user=self._make_user(scopes=["api:read"]))
        assert ctx.has_scope("api:read") is True
        assert ctx.has_scope("api:write") is False

    # ------------------------------------------------------------------
    # require_scope
    # ------------------------------------------------------------------
    def test_require_scope_delegates(self):
        ctx = self._make_ctx(user=self._make_user(scopes=["api:read"]))
        # Should not raise
        ctx.require_scope("api:read")

    def test_require_scope_raises(self):
        ctx = self._make_ctx(user=self._make_user(scopes=[]))
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_scope("api:write")
        assert exc_info.value.status_code == 403

    # ------------------------------------------------------------------
    # is_tenant_owner
    # ------------------------------------------------------------------
    def test_is_tenant_owner_true(self):
        member = MagicMock()
        member.is_owner = True
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.is_tenant_owner is True

    def test_is_tenant_owner_false(self):
        member = MagicMock()
        member.is_owner = False
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.is_tenant_owner is False

    def test_is_tenant_owner_no_member(self):
        ctx = self._make_ctx(tenant_member=None)
        assert ctx.is_tenant_owner is False

    # ------------------------------------------------------------------
    # is_tenant_admin
    # ------------------------------------------------------------------
    def test_is_tenant_admin_true(self):
        member = MagicMock()
        member.is_admin = True
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.is_tenant_admin is True

    def test_is_tenant_admin_false(self):
        member = MagicMock()
        member.is_admin = False
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.is_tenant_admin is False

    def test_is_tenant_admin_no_member(self):
        ctx = self._make_ctx(tenant_member=None)
        assert ctx.is_tenant_admin is False

    # ------------------------------------------------------------------
    # can_manage_members
    # ------------------------------------------------------------------
    def test_can_manage_members_true(self):
        member = MagicMock()
        member.can_manage_members = True
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.can_manage_members is True

    def test_can_manage_members_false(self):
        member = MagicMock()
        member.can_manage_members = False
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.can_manage_members is False

    def test_can_manage_members_no_member(self):
        ctx = self._make_ctx(tenant_member=None)
        assert ctx.can_manage_members is False

    # ------------------------------------------------------------------
    # can_manage_tenant
    # ------------------------------------------------------------------
    def test_can_manage_tenant_true(self):
        member = MagicMock()
        member.can_manage_tenant = True
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.can_manage_tenant is True

    def test_can_manage_tenant_false(self):
        member = MagicMock()
        member.can_manage_tenant = False
        ctx = self._make_ctx(tenant_member=member)
        assert ctx.can_manage_tenant is False

    def test_can_manage_tenant_no_member(self):
        ctx = self._make_ctx(tenant_member=None)
        assert ctx.can_manage_tenant is False

    # ------------------------------------------------------------------
    # require_tenant_admin
    # ------------------------------------------------------------------
    def test_require_tenant_admin_passes(self):
        member = MagicMock()
        member.is_admin = True
        ctx = self._make_ctx(tenant_member=member)
        # Should not raise
        ctx.require_tenant_admin()

    def test_require_tenant_admin_raises(self):
        member = MagicMock()
        member.is_admin = False
        ctx = self._make_ctx(tenant_member=member)
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_tenant_admin()
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()

    def test_require_tenant_admin_no_member_raises(self):
        ctx = self._make_ctx(tenant_member=None)
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_tenant_admin()
        assert exc_info.value.status_code == 403
