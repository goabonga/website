# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the authentication and database models."""

import uuid

import pytest
from internal.auth.models import User


class TestUserFromJwtClaims:
    def test_from_jwt_claims(self):
        claims = {
            "sub": "12345678-1234-5678-1234-567812345678",
            "email": "user@example.com",
            "name": "Test User",
            "scope": "knowledge:read prompts:write",
        }
        user = User.from_jwt_claims(claims)
        assert user.id == uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert user.email == "user@example.com"
        assert user.name == "Test User"
        assert user.scopes == ["knowledge:read", "prompts:write"]

    def test_from_jwt_claims_preferred_username(self):
        claims = {
            "sub": "12345678-1234-5678-1234-567812345678",
            "preferred_username": "testuser",
            "scope": "",
        }
        user = User.from_jwt_claims(claims)
        assert user.name == "testuser"
        assert user.scopes == []

    def test_from_jwt_claims_missing_sub(self):
        with pytest.raises(ValueError, match="JWT missing 'sub' claim"):
            User.from_jwt_claims({"email": "user@example.com"})

    def test_from_jwt_claims_empty_scope(self):
        claims = {"sub": "12345678-1234-5678-1234-567812345678"}
        user = User.from_jwt_claims(claims)
        assert user.scopes == []


class TestUserHasScope:
    def test_exact_match(self, mock_user):
        assert mock_user.has_scope("knowledge:read") is True
        assert mock_user.has_scope("knowledge:delete") is False

    def test_wildcard_star(self, mock_admin_user):
        assert mock_admin_user.has_scope("anything:read") is True
        assert mock_admin_user.has_scope("whatever") is True

    def test_resource_wildcard(self):
        user = User(id=uuid.uuid4(), scopes=["knowledge:*"])
        assert user.has_scope("knowledge:read") is True
        assert user.has_scope("knowledge:write") is True
        assert user.has_scope("knowledge:delete") is True
        assert user.has_scope("prompts:read") is False

    def test_internal_wildcard(self):
        user = User(id=uuid.uuid4(), scopes=["internal:*"])
        assert user.has_scope("namespaces:read") is True
        assert user.has_scope("prompts:write") is True
        assert user.has_scope("knowledge:delete") is True
        assert user.has_scope("conversations:read") is True

    def test_internal_wildcard_non_internal_resource(self):
        user = User(id=uuid.uuid4(), scopes=["internal:*"])
        assert user.has_scope("users:read") is False
        assert user.has_scope("billing:write") is False

    def test_no_scopes(self):
        user = User(id=uuid.uuid4(), scopes=[])
        assert user.has_scope("knowledge:read") is False


class TestUserScopeHelpers:
    def test_has_any_scope(self, mock_user):
        assert mock_user.has_any_scope(["knowledge:read", "users:admin"]) is True
        assert mock_user.has_any_scope(["users:admin", "billing:read"]) is False

    def test_has_all_scopes(self, mock_user):
        assert mock_user.has_all_scopes(["knowledge:read", "prompts:read"]) is True
        assert mock_user.has_all_scopes(["knowledge:read", "users:admin"]) is False

    def test_can_write(self, mock_user):
        assert mock_user.can_write("knowledge") is True
        assert mock_user.can_write("prompts") is False

    def test_can_delete(self, mock_user):
        assert mock_user.can_delete("knowledge") is False

    def test_admin_can_write_and_delete(self, mock_admin_user):
        assert mock_admin_user.can_write("anything") is True
        assert mock_admin_user.can_delete("anything") is True
