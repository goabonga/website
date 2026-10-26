# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.deps — FastAPI dependency injection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestBearerTokenAuth:
    def test_fields(self):
        from auth.api.deps import BearerTokenAuth

        auth = BearerTokenAuth(client_id="c1", scopes=["read"], subject="u1")
        assert auth.client_id == "c1"
        assert auth.scopes == ["read"]
        assert auth.subject == "u1"

    def test_defaults(self):
        from auth.api.deps import BearerTokenAuth

        auth = BearerTokenAuth(client_id="c1", scopes=[])
        assert auth.subject is None


class TestPATAuth:
    def test_fields(self):
        from auth.api.deps import PATAuth

        auth = PATAuth(
            user_id="u1",
            pat_id="p1",
            scopes=["read"],
            tenant_id="t1",
            target_client_id="c1",
        )
        assert auth.user_id == "u1"
        assert auth.pat_id == "p1"
        assert auth.scopes == ["read"]
        assert auth.tenant_id == "t1"
        assert auth.target_client_id == "c1"

    def test_defaults(self):
        from auth.api.deps import PATAuth

        auth = PATAuth(user_id="u1", pat_id="p1", scopes=[])
        assert auth.tenant_id is None
        assert auth.target_client_id is None


# ---------------------------------------------------------------------------
# get_db
# ---------------------------------------------------------------------------


class TestGetDb:
    @pytest.mark.asyncio
    @patch("auth.api.deps.async_session_factory")
    async def test_yields_session_and_commits(self, mock_factory):
        from auth.api.deps import get_db

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        gen = get_db()
        session = await gen.__anext__()
        assert session is mock_session

        # Exhaust the generator (triggers commit)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("auth.api.deps.async_session_factory")
    async def test_rollback_on_exception(self, mock_factory):
        from auth.api.deps import get_db

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        gen = get_db()
        await gen.__anext__()

        # Simulate an exception during yield
        with pytest.raises(ValueError):
            await gen.athrow(ValueError("boom"))

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_encryption
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------


class TestServiceFactories:
    def test_get_templates(self):
        from auth.api.deps import get_templates

        get_templates.cache_clear()
        result = get_templates()
        assert result is not None
        get_templates.cache_clear()


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# get_current_user_with_roles
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# validate_bearer_token
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# validate_pat_token
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# token_has_scope
# ---------------------------------------------------------------------------


class TestTokenHasScope:
    def test_exact_match(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:read", "users:write"], "users:read") is True

    def test_no_match(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:read"], "users:write") is False

    def test_wildcard_match(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:*"], "users:read") is True
        assert token_has_scope(["users:*"], "users:write") is True

    def test_wildcard_no_match_different_prefix(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:*"], "clients:read") is False

    def test_global_wildcard(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["*"], "anything:here") is True

    def test_empty_scopes(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope([], "users:read") is False


# ---------------------------------------------------------------------------
# user_has_scope
# ---------------------------------------------------------------------------


class TestUserHasScope:
    def test_role_has_scope(self):
        from auth.api.deps import user_has_scope

        role = MagicMock()
        role.has_scope.return_value = True

        assert user_has_scope([role], "users:read") is True
        role.has_scope.assert_called_with("users:read")

    def test_no_role_has_scope(self):
        from auth.api.deps import user_has_scope

        role = MagicMock()
        role.has_scope.return_value = False

        assert user_has_scope([role], "users:read") is False

    def test_empty_roles(self):
        from auth.api.deps import user_has_scope

        assert user_has_scope([], "users:read") is False

    def test_multiple_roles_second_matches(self):
        from auth.api.deps import user_has_scope

        role1 = MagicMock()
        role1.has_scope.return_value = False
        role2 = MagicMock()
        role2.has_scope.return_value = True

        assert user_has_scope([role1, role2], "users:read") is True


# ---------------------------------------------------------------------------
# require_scope
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# require_any_scope
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# get_user_admin_permissions
# ---------------------------------------------------------------------------


class TestGetUserAdminPermissions:
    def test_no_roles_all_false(self):
        from auth.api.deps import get_user_admin_permissions

        perms = get_user_admin_permissions([])

        assert perms["can_view_dashboard"] is False
        assert perms["can_view_users"] is False
        assert perms["users:read"] is False
        assert perms["users:write"] is False

    def test_admin_with_all_scopes(self):
        from auth.api.deps import get_user_admin_permissions

        role = MagicMock()
        role.has_scope.return_value = True

        perms = get_user_admin_permissions([role])

        assert perms["can_view_dashboard"] is True
        assert perms["can_view_users"] is True
        assert perms["can_view_clients"] is True
        assert perms["can_view_sessions"] is True
        assert perms["can_view_jwks"] is True
        assert perms["can_view_roles"] is True
        assert perms["can_view_scopes"] is True
        assert perms["can_view_orgs"] is True
        assert perms["can_view_pats"] is True
        assert perms["users:read"] is True
        assert perms["users:write"] is True
        assert perms["users:delete"] is True
        assert perms["users:disable"] is True
        assert perms["clients:read"] is True
        assert perms["clients:write"] is True
        assert perms["clients:delete"] is True
        assert perms["clients:rotate"] is True
        assert perms["sessions:read"] is True
        assert perms["sessions:revoke"] is True
        assert perms["roles:read"] is True
        assert perms["roles:write"] is True
        assert perms["roles:delete"] is True
        assert perms["roles:assign"] is True
        assert perms["scopes:read"] is True
        assert perms["scopes:write"] is True
        assert perms["scopes:delete"] is True
        assert perms["jwks:read"] is True
        assert perms["jwks:write"] is True
        assert perms["jwks:delete"] is True
        assert perms["jwks:revoke"] is True
        assert perms["jwks:rotate"] is True
        assert perms["org:read"] is True
        assert perms["org:write"] is True
        assert perms["org:delete"] is True
        assert perms["pats:read"] is True
        assert perms["pats:revoke"] is True

    def test_partial_scopes(self):
        from auth.api.deps import get_user_admin_permissions

        role = MagicMock()
        # Only users:read scope
        role.has_scope.side_effect = lambda s: s == "users:read"

        perms = get_user_admin_permissions([role])

        assert perms["can_view_dashboard"] is True  # users:read is in the dashboard check
        assert perms["can_view_users"] is True
        assert perms["users:read"] is True
        assert perms["users:write"] is False
        assert perms["can_view_clients"] is False
        assert perms["clients:read"] is False
