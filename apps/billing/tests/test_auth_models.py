# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/auth/models.py."""

from uuid import UUID

import pytest
from billing.auth.models import User


class TestUserFromJwtClaims:
    """Tests for User.from_jwt_claims()."""

    def test_uuid_subject_creates_user(self):
        """Create user with UUID subject."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "email": "user@example.com",
            "name": "Test User",
            "scope": "openid profile",
            "client_id": "my-app",
        }
        user = User.from_jwt_claims(claims)
        assert isinstance(user.id, UUID)
        assert str(user.id) == "550e8400-e29b-41d4-a716-446655440000"
        assert user.email == "user@example.com"
        assert user.name == "Test User"
        assert user.scopes == ["openid", "profile"]
        assert user.client_id == "my-app"
        assert user.is_machine_client is False

    def test_non_uuid_subject_creates_machine_client(self):
        """Non-UUID subject is detected as machine client."""
        claims = {"sub": "my-service", "scope": "resource:read"}
        user = User.from_jwt_claims(claims)
        assert user.id == "my-service"
        assert user.is_machine_client is True

    def test_client_id_equals_sub_creates_machine_client(self):
        """client_id == sub indicates machine client."""
        claims = {"sub": "service-name", "client_id": "service-name", "scope": ""}
        user = User.from_jwt_claims(claims)
        assert user.is_machine_client is True
        assert user.id == "service-name"

    def test_client_id_equals_sub_with_uuid(self):
        """client_id == sub takes priority even when sub is valid UUID."""
        uid = "550e8400-e29b-41d4-a716-446655440000"
        claims = {"sub": uid, "client_id": uid, "scope": ""}
        user = User.from_jwt_claims(claims)
        assert user.is_machine_client is True

    def test_uuid_subject_with_different_client_id(self):
        """UUID sub with different client_id is not a machine client."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "client_id": "other-client",
            "scope": "",
        }
        user = User.from_jwt_claims(claims)
        assert user.is_machine_client is False
        assert isinstance(user.id, UUID)
        assert user.client_id == "other-client"

    def test_missing_sub_raises_value_error(self):
        """Raise ValueError when 'sub' claim is missing."""
        with pytest.raises(ValueError, match="JWT missing 'sub' claim"):
            User.from_jwt_claims({"scope": "openid"})

    def test_empty_sub_raises_value_error(self):
        """Raise ValueError when 'sub' claim is empty string."""
        with pytest.raises(ValueError, match="JWT missing 'sub' claim"):
            User.from_jwt_claims({"sub": "", "scope": ""})

    def test_none_sub_raises_value_error(self):
        """Raise ValueError when 'sub' claim is None."""
        with pytest.raises(ValueError, match="JWT missing 'sub' claim"):
            User.from_jwt_claims({"sub": None, "scope": ""})

    def test_space_separated_scopes_are_split(self):
        """Space-separated scope string is split into list."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "scope": "openid profile email resource:read",
        }
        user = User.from_jwt_claims(claims)
        assert user.scopes == ["openid", "profile", "email", "resource:read"]

    def test_single_scope(self):
        """Single scope string becomes one-element list."""
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000", "scope": "resource:read"}
        user = User.from_jwt_claims(claims)
        assert user.scopes == ["resource:read"]

    def test_scope_as_list(self):
        """Scope as list is preserved."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "scope": ["resource:read", "resource:write"],
        }
        user = User.from_jwt_claims(claims)
        assert user.scopes == ["resource:read", "resource:write"]

    def test_scp_string_fallback(self):
        """Fall back to 'scp' claim when 'scope' is absent."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "scp": "resource:read resource:write",
        }
        user = User.from_jwt_claims(claims)
        assert user.scopes == ["resource:read", "resource:write"]

    def test_scp_list_fallback(self):
        """Fall back to 'scp' claim as list."""
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000", "scp": ["resource:read"]}
        user = User.from_jwt_claims(claims)
        assert user.scopes == ["resource:read"]

    def test_scope_takes_precedence_over_scp(self):
        """'scope' claim takes precedence over 'scp'."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "scope": "resource:read",
            "scp": "admin:write",
        }
        user = User.from_jwt_claims(claims)
        assert user.scopes == ["resource:read"]

    def test_empty_scope_returns_empty_list(self):
        """Empty scope string returns empty list."""
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000", "scope": ""}
        user = User.from_jwt_claims(claims)
        assert user.scopes == []

    def test_missing_scope_returns_empty_list(self):
        """No scope or scp claim returns empty list."""
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000"}
        user = User.from_jwt_claims(claims)
        assert user.scopes == []

    def test_non_standard_scope_type_returns_empty(self):
        """Non-string, non-list scope type returns empty list."""
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000", "scope": 12345}
        user = User.from_jwt_claims(claims)
        assert user.scopes == []

    def test_preferred_username_fallback(self):
        """Use preferred_username when name is absent."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "preferred_username": "jdoe",
            "scope": "",
        }
        user = User.from_jwt_claims(claims)
        assert user.name == "jdoe"

    def test_name_takes_precedence_over_preferred_username(self):
        """'name' claim takes precedence over 'preferred_username'."""
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "name": "John Doe",
            "preferred_username": "jdoe",
            "scope": "",
        }
        user = User.from_jwt_claims(claims)
        assert user.name == "John Doe"

    def test_no_name_or_preferred_username(self):
        """Name is None when neither 'name' nor 'preferred_username' is set."""
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000", "scope": ""}
        user = User.from_jwt_claims(claims)
        assert user.name is None

    def test_optional_fields_default_to_none(self):
        """Optional fields default to None when absent."""
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000", "scope": ""}
        user = User.from_jwt_claims(claims)
        assert user.email is None
        assert user.name is None
        assert user.client_id is None


class TestUserHasScope:
    """Tests for User.has_scope()."""

    def test_exact_match(self):
        user = User(id="u1", scopes=["resource:read"])
        assert user.has_scope("resource:read") is True

    def test_no_match(self):
        user = User(id="u1", scopes=["resource:read"])
        assert user.has_scope("resource:write") is False

    def test_global_wildcard(self):
        user = User(id="u1", scopes=["*"])
        assert user.has_scope("anything") is True

    def test_prefix_wildcard_match(self):
        user = User(id="u1", scopes=["resource:*"])
        assert user.has_scope("resource:read") is True

    def test_prefix_wildcard_multi_level(self):
        """Prefix wildcard matches multi-level scopes."""
        user = User(id="u1", scopes=["resource:*"])
        assert user.has_scope("resource:deep:nested") is True

    def test_prefix_wildcard_no_match(self):
        user = User(id="u1", scopes=["resource:*"])
        assert user.has_scope("admin:read") is False

    def test_empty_scopes(self):
        user = User(id="u1", scopes=[])
        assert user.has_scope("resource:read") is False

    def test_multiple_wildcards(self):
        user = User(id="u1", scopes=["resource:*", "admin:*"])
        assert user.has_scope("resource:read") is True
        assert user.has_scope("admin:write") is True
        assert user.has_scope("other:read") is False

    def test_wildcard_with_exact_coexist(self):
        user = User(id="u1", scopes=["resource:*", "users:read"])
        assert user.has_scope("resource:write") is True
        assert user.has_scope("users:read") is True
        assert user.has_scope("users:write") is False


class TestUserHasAnyScope:
    """Tests for User.has_any_scope()."""

    def test_has_one_of_multiple(self):
        user = User(id="u1", scopes=["resource:read"])
        assert user.has_any_scope(["resource:read", "resource:write"]) is True

    def test_has_none(self):
        user = User(id="u1", scopes=["resource:read"])
        assert user.has_any_scope(["admin:read", "admin:write"]) is False

    def test_empty_required(self):
        user = User(id="u1", scopes=["resource:read"])
        assert user.has_any_scope([]) is False

    def test_wildcard_match(self):
        user = User(id="u1", scopes=["resource:*"])
        assert user.has_any_scope(["resource:read", "admin:write"]) is True


class TestUserHasAllScopes:
    """Tests for User.has_all_scopes()."""

    def test_has_all(self):
        user = User(id="u1", scopes=["resource:read", "resource:write"])
        assert user.has_all_scopes(["resource:read", "resource:write"]) is True

    def test_missing_one(self):
        user = User(id="u1", scopes=["resource:read"])
        assert user.has_all_scopes(["resource:read", "resource:write"]) is False

    def test_empty_required(self):
        user = User(id="u1", scopes=["resource:read"])
        assert user.has_all_scopes([]) is True

    def test_wildcard_covers_all(self):
        user = User(id="u1", scopes=["resource:*"])
        assert user.has_all_scopes(["resource:read", "resource:write"]) is True
