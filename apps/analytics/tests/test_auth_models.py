# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.auth.models module."""

from uuid import UUID

import pytest
from analytics.auth.models import User


class TestUserFromJwtClaims:
    """Tests for User.from_jwt_claims classmethod."""

    def test_user_token_with_uuid_subject(self):
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "email": "user@example.com",
            "name": "Test User",
            "scope": "analytics:read analytics:write",
        }
        user = User.from_jwt_claims(claims)
        assert isinstance(user.id, UUID)
        assert user.email == "user@example.com"
        assert user.name == "Test User"
        assert user.scopes == ["analytics:read", "analytics:write"]
        assert user.is_machine_client is False

    def test_machine_token_with_string_subject(self):
        claims = {
            "sub": "my-service-client",
            "scope": "analytics:read",
        }
        user = User.from_jwt_claims(claims)
        assert user.id == "my-service-client"
        assert user.is_machine_client is True

    def test_missing_sub_raises_error(self):
        with pytest.raises(ValueError, match="missing 'sub'"):
            User.from_jwt_claims({"email": "user@example.com"})

    def test_scope_as_list(self):
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "scp": ["analytics:read", "analytics:write"],
        }
        user = User.from_jwt_claims(claims)
        assert user.scopes == ["analytics:read", "analytics:write"]

    def test_empty_scope(self):
        claims = {"sub": "550e8400-e29b-41d4-a716-446655440000"}
        user = User.from_jwt_claims(claims)
        assert user.scopes == []

    def test_preferred_username_fallback(self):
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "preferred_username": "testuser",
        }
        user = User.from_jwt_claims(claims)
        assert user.name == "testuser"

    def test_scope_as_non_string_non_list(self):
        claims = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "scope": 123,
        }
        user = User.from_jwt_claims(claims)
        assert user.scopes == []


class TestUserHasScope:
    """Tests for User.has_scope method."""

    def test_exact_match(self):
        user = User(id="test", scopes=["analytics:read"])
        assert user.has_scope("analytics:read") is True
        assert user.has_scope("analytics:write") is False

    def test_global_wildcard(self):
        user = User(id="test", scopes=["*"])
        assert user.has_scope("analytics:read") is True
        assert user.has_scope("anything") is True

    def test_resource_wildcard(self):
        user = User(id="test", scopes=["analytics:*"])
        assert user.has_scope("analytics:read") is True
        assert user.has_scope("analytics:write") is True
        assert user.has_scope("other:read") is False

    def test_no_scopes(self):
        user = User(id="test", scopes=[])
        assert user.has_scope("analytics:read") is False


class TestUserHasAnyScope:
    """Tests for User.has_any_scope method."""

    def test_has_one_of_required(self):
        user = User(id="test", scopes=["analytics:read"])
        assert user.has_any_scope(["analytics:read", "analytics:write"]) is True

    def test_has_none_of_required(self):
        user = User(id="test", scopes=["other:read"])
        assert user.has_any_scope(["analytics:read", "analytics:write"]) is False


class TestUserHasAllScopes:
    """Tests for User.has_all_scopes method."""

    def test_has_all_required(self):
        user = User(id="test", scopes=["analytics:read", "analytics:write"])
        assert user.has_all_scopes(["analytics:read", "analytics:write"]) is True

    def test_missing_one_required(self):
        user = User(id="test", scopes=["analytics:read"])
        assert user.has_all_scopes(["analytics:read", "analytics:write"]) is False
