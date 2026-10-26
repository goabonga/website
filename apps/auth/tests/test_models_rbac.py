# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.models.rbac — RBAC model methods and properties."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from auth.db.models.rbac import (
    ADMIN_SCOPES,
    DEFAULT_ROLES,
    Role,
    RoleScope,
    Scope,
    UserRole,
)


def _make_scope_obj(name, is_active=True):
    """Create a mock Scope."""
    s = MagicMock()
    s.name = name
    s.is_active = is_active
    return s


def _make_role_scope(scope):
    """Create a mock RoleScope with a given scope."""
    rs = MagicMock()
    rs.scope = scope
    return rs


def _make_role(role_scopes):
    """Create a mock Role with real has_scope / get_all_scope_names methods."""
    role = MagicMock(spec=Role)
    role.role_scopes = role_scopes
    role.has_scope = lambda req: Role.has_scope(role, req)
    role.get_all_scope_names = lambda: Role.get_all_scope_names(role)
    return role


class TestRoleHasScope:
    def test_global_wildcard(self):
        role = _make_role([_make_role_scope(_make_scope_obj("*"))])
        assert role.has_scope("users:read") is True

    def test_exact_match(self):
        role = _make_role([_make_role_scope(_make_scope_obj("users:read"))])
        assert role.has_scope("users:read") is True

    def test_resource_wildcard(self):
        role = _make_role([_make_role_scope(_make_scope_obj("users:*"))])
        assert role.has_scope("users:read") is True
        assert role.has_scope("users:write") is True

    def test_no_match(self):
        role = _make_role([_make_role_scope(_make_scope_obj("clients:read"))])
        assert role.has_scope("users:read") is False

    def test_inactive_scope_ignored(self):
        role = _make_role([_make_role_scope(_make_scope_obj("users:read", is_active=False))])
        assert role.has_scope("users:read") is False

    def test_null_scope_ignored(self):
        rs = MagicMock()
        rs.scope = None
        role = _make_role([rs])
        assert role.has_scope("users:read") is False

    def test_empty_role_scopes(self):
        role = _make_role([])
        assert role.has_scope("users:read") is False

    def test_multiple_scopes(self):
        role = _make_role(
            [
                _make_role_scope(_make_scope_obj("clients:read")),
                _make_role_scope(_make_scope_obj("users:read")),
            ]
        )
        assert role.has_scope("users:read") is True
        assert role.has_scope("clients:read") is True
        assert role.has_scope("sessions:read") is False


class TestGetAllScopeNames:
    def test_returns_active_scope_names(self):
        role = _make_role(
            [
                _make_role_scope(_make_scope_obj("users:read")),
                _make_role_scope(_make_scope_obj("clients:write")),
            ]
        )
        names = role.get_all_scope_names()
        assert names == ["users:read", "clients:write"]

    def test_skips_inactive(self):
        role = _make_role(
            [
                _make_role_scope(_make_scope_obj("users:read", is_active=False)),
                _make_role_scope(_make_scope_obj("clients:write")),
            ]
        )
        names = role.get_all_scope_names()
        assert names == ["clients:write"]

    def test_skips_null_scope(self):
        rs = MagicMock()
        rs.scope = None
        role = _make_role([rs])
        names = role.get_all_scope_names()
        assert names == []

    def test_empty(self):
        role = _make_role([])
        names = role.get_all_scope_names()
        assert names == []


class TestUserRoleIsExpired:
    def _make_user_role(self, expires_at):
        ur = MagicMock(spec=UserRole)
        ur.expires_at = expires_at
        type(ur).is_expired = UserRole.is_expired
        return ur

    def test_no_expiration(self):
        ur = self._make_user_role(None)
        assert ur.is_expired is False

    def test_future_expiration(self):
        ur = self._make_user_role(datetime.now(UTC) + timedelta(days=30))
        assert ur.is_expired is False

    def test_past_expiration(self):
        ur = self._make_user_role(datetime.now(UTC) - timedelta(days=1))
        assert ur.is_expired is True


class TestRepr:
    def test_scope_repr(self):
        s = MagicMock(spec=Scope)
        s.name = "users:read"
        s.category = "admin"
        s.__repr__ = Scope.__repr__
        assert "users:read" in repr(s)

    def test_role_repr(self):
        r = MagicMock(spec=Role)
        r.name = "admin"
        r.__repr__ = Role.__repr__
        assert "admin" in repr(r)

    def test_role_scope_repr(self):
        rs = MagicMock(spec=RoleScope)
        rs.role_id = uuid.uuid4()
        rs.scope_id = uuid.uuid4()
        rs.__repr__ = RoleScope.__repr__
        result = repr(rs)
        assert "RoleScope" in result

    def test_user_role_repr(self):
        ur = MagicMock(spec=UserRole)
        ur.user_id = uuid.uuid4()
        ur.role_id = uuid.uuid4()
        ur.__repr__ = UserRole.__repr__
        result = repr(ur)
        assert "UserRole" in result


class TestConstants:
    def test_admin_scopes_contains_wildcard(self):
        assert "*" in ADMIN_SCOPES

    def test_admin_scopes_cover_the_organisation_api(self):
        for name in ("org:*", "org:read", "org:write", "org:delete"):
            assert name in ADMIN_SCOPES

    def test_default_roles_only_use_declared_scopes(self):
        for name, config in DEFAULT_ROLES.items():
            unknown = set(config["scopes"]) - set(ADMIN_SCOPES)
            assert not unknown, (name, unknown)

    def test_no_scope_of_another_service_is_built_in(self):
        resources = {name.split(":")[0] for name in ADMIN_SCOPES}
        assert resources == {
            "*",
            "users",
            "clients",
            "sessions",
            "jwks",
            "roles",
            "scopes",
            "org",
            "pats",
        }

    def test_default_roles_has_super_admin(self):
        assert "super_admin" in DEFAULT_ROLES
        assert DEFAULT_ROLES["super_admin"]["scopes"] == ["*"]

    def test_readonly_role_reads_what_the_scopes_pages_show(self):
        """The scopes pages follow `scopes:*`: the read-only role keeps the list of scopes."""
        assert "scopes:read" in DEFAULT_ROLES["readonly"]["scopes"]

    def test_only_super_admin_changes_scopes_by_default(self):
        for name, config in DEFAULT_ROLES.items():
            writes = {"scopes:*", "scopes:write", "scopes:delete"} & set(config["scopes"])
            assert not writes, name
