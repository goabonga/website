# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.tokens — PAT management endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_user

MODULE = "auth.api.routes.auth.tokens"


def _mock_request(cookies=None, headers=None, url_path="/auth/settings/tokens", query=""):
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = MagicMock()
    request.headers.get = MagicMock(side_effect=lambda k, d=None: (headers or {}).get(k, d))
    request.url = MagicMock()
    request.url.scheme = "https"
    request.url.netloc = "auth.example.com"
    request.url.path = url_path
    request.url.query = query
    return request


def _make_pat(**overrides):
    pat = MagicMock()
    pat.id = overrides.get("id", uuid.uuid4())
    pat.name = overrides.get("name", "My Token")
    pat.description = overrides.get("description", "A test token")
    pat.scopes = overrides.get("scopes", ["read:profile"])
    pat.token_suffix = overrides.get("token_suffix", "abc123")
    pat.created_at = overrides.get("created_at", datetime(2025, 1, 1, tzinfo=UTC))
    pat.expires_at = overrides.get("expires_at", datetime(2025, 4, 1, tzinfo=UTC))
    pat.last_used_at = overrides.get("last_used_at")
    pat.last_used_ip = overrides.get("last_used_ip")
    pat.use_count = overrides.get("use_count", 0)
    pat.is_expired = overrides.get("is_expired", False)
    pat.revoked_at = overrides.get("revoked_at")
    pat.tenant_id = overrides.get("tenant_id")
    pat.target_client_id = overrides.get("target_client_id")
    return pat


# ---------------------------------------------------------------------------
# get_tenant_prefix
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.tokens import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_path_resolution(self, mock_ctx):
        from auth.api.routes.auth.tokens import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/acme"


# ---------------------------------------------------------------------------
# pat_to_response
# ---------------------------------------------------------------------------


class TestPatToResponse:
    def test_basic(self):
        from auth.api.routes.auth.tokens import pat_to_response

        pat = _make_pat()
        resp = pat_to_response(pat)
        assert resp.id == str(pat.id)
        assert resp.name == "My Token"
        assert resp.scopes == ["read:profile"]
        assert resp.is_revoked is False

    def test_revoked(self):
        from auth.api.routes.auth.tokens import pat_to_response

        pat = _make_pat(revoked_at=datetime(2025, 2, 1, tzinfo=UTC))
        resp = pat_to_response(pat)
        assert resp.is_revoked is True

    def test_with_tenant_and_client(self):
        from auth.api.routes.auth.tokens import pat_to_response

        tid = uuid.uuid4()
        cid = uuid.uuid4()
        pat = _make_pat(tenant_id=tid, target_client_id=cid)
        resp = pat_to_response(pat)
        assert resp.tenant_id == str(tid)
        assert resp.target_client_id == str(cid)

    def test_none_tenant_and_client(self):
        from auth.api.routes.auth.tokens import pat_to_response

        pat = _make_pat(tenant_id=None, target_client_id=None)
        resp = pat_to_response(pat)
        assert resp.tenant_id is None
        assert resp.target_client_id is None


# ---------------------------------------------------------------------------
# get_user_available_scopes
# ---------------------------------------------------------------------------


class TestGetUserAvailableScopes:
    @pytest.mark.asyncio
    async def test_with_wildcard(self):
        from auth.api.routes.auth.tokens import get_user_available_scopes

        db = AsyncMock()
        user = make_user()

        # Mock roles query — user has wildcard
        wildcard_scope = MagicMock()
        wildcard_scope.name = "*"
        wildcard_scope.is_active = True

        rs = MagicMock()
        rs.scope = wildcard_scope

        role = MagicMock()
        role.role_scopes = [rs]

        # Mock all scopes query
        scope1 = MagicMock()
        scope1.name = "read:profile"
        scope1.description = "Read profile"
        scope1.resource = "profile"
        scope1.action = "read"
        scope1.category = "user"

        scope2 = MagicMock()
        scope2.name = "write:profile"
        scope2.description = "Write profile"
        scope2.resource = "profile"
        scope2.action = "write"
        scope2.category = "user"

        with (
            patch(
                f"{MODULE}.role_service.list_user_roles_with_scopes",
                new=AsyncMock(return_value=[role]),
            ),
            patch(
                f"{MODULE}.scope_service.list_active",
                new=AsyncMock(return_value=[scope1, scope2]),
            ) as mock_list_active,
        ):
            result = await get_user_available_scopes(db, user)

        # Wildcard: called with names=None to get every active scope
        assert mock_list_active.await_args.kwargs["names"] is None

        # Result is a dict keyed by category label, with builtins always present
        assert isinstance(result, dict)
        assert "USER" in result
        # User category has a Profile resource with 2 scopes
        assert "Profile" in result["USER"]
        assert len(result["USER"]["Profile"]) == 2
        # Builtins are always merged
        assert "OIDC" in result
        assert "System" in result

    @pytest.mark.asyncio
    async def test_without_wildcard(self):
        from auth.api.routes.auth.tokens import get_user_available_scopes

        db = AsyncMock()
        user = make_user()

        # Mock roles query — user has specific scopes
        scope_obj = MagicMock()
        scope_obj.name = "read:profile"
        scope_obj.is_active = True

        rs = MagicMock()
        rs.scope = scope_obj

        role = MagicMock()
        role.role_scopes = [rs]

        # Mock filtered scopes query
        scope1 = MagicMock()
        scope1.name = "read:profile"
        scope1.description = "Read profile"
        scope1.resource = "profile"
        scope1.action = "read"
        scope1.category = "user"

        with (
            patch(
                f"{MODULE}.role_service.list_user_roles_with_scopes",
                new=AsyncMock(return_value=[role]),
            ),
            patch(
                f"{MODULE}.scope_service.list_active",
                new=AsyncMock(return_value=[scope1]),
            ) as mock_list_active,
        ):
            result = await get_user_available_scopes(db, user)

        # Non-wildcard: called with the user's scope-name set
        assert mock_list_active.await_args.kwargs["names"] == {"read:profile"}

        # Result is a dict keyed by category label
        assert isinstance(result, dict)
        assert "USER" in result
        # User -> Profile -> list of (name, description) tuples
        assert "Profile" in result["USER"]
        scope_names = [s[0] for s in result["USER"]["Profile"]]
        assert "read:profile" in scope_names

    @pytest.mark.asyncio
    async def test_no_roles(self):
        from auth.api.routes.auth.tokens import get_user_available_scopes

        db = AsyncMock()
        user = make_user()

        with (
            patch(
                f"{MODULE}.role_service.list_user_roles_with_scopes",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                f"{MODULE}.scope_service.list_active",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await get_user_available_scopes(db, user)

        # No DB scopes but builtins are always present
        assert isinstance(result, dict)
        assert "OIDC" in result
        assert "System" in result

    @pytest.mark.asyncio
    async def test_inactive_scope_ignored(self):
        from auth.api.routes.auth.tokens import get_user_available_scopes

        db = AsyncMock()
        user = make_user()

        inactive_scope = MagicMock()
        inactive_scope.name = "admin:all"
        inactive_scope.is_active = False

        rs = MagicMock()
        rs.scope = inactive_scope

        role = MagicMock()
        role.role_scopes = [rs]

        with (
            patch(
                f"{MODULE}.role_service.list_user_roles_with_scopes",
                new=AsyncMock(return_value=[role]),
            ),
            patch(
                f"{MODULE}.scope_service.list_active",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await get_user_available_scopes(db, user)
        # No DB scopes for the inactive scope but builtins are always present
        assert isinstance(result, dict)
        assert "OIDC" in result
        assert "System" in result
        # The inactive scope should NOT appear
        all_scope_names = set()
        for resources in result.values():
            for scope_pairs in resources.values():
                for name, _desc in scope_pairs:
                    all_scope_names.add(name)
        assert "admin:all" not in all_scope_names

    @pytest.mark.asyncio
    async def test_multiple_categories(self):
        from auth.api.routes.auth.tokens import get_user_available_scopes

        db = AsyncMock()
        user = make_user()

        wildcard = MagicMock()
        wildcard.name = "*"
        wildcard.is_active = True

        rs = MagicMock()
        rs.scope = wildcard

        role = MagicMock()
        role.role_scopes = [rs]

        scope1 = MagicMock()
        scope1.name = "read:profile"
        scope1.description = "Read"
        scope1.resource = "profile"
        scope1.action = "read"
        scope1.category = "user"

        scope2 = MagicMock()
        scope2.name = "admin:users"
        scope2.description = "Admin users"
        scope2.resource = "users"
        scope2.action = "admin"
        scope2.category = "admin"

        with (
            patch(
                f"{MODULE}.role_service.list_user_roles_with_scopes",
                new=AsyncMock(return_value=[role]),
            ),
            patch(
                f"{MODULE}.scope_service.list_active",
                new=AsyncMock(return_value=[scope1, scope2]),
            ),
        ):
            result = await get_user_available_scopes(db, user)
        # Result is a dict keyed by category labels
        assert isinstance(result, dict)
        assert "USER" in result
        assert "Admin" in result


# ---------------------------------------------------------------------------
# tokens_page
# ---------------------------------------------------------------------------


class TestTokensPage:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_pat_service")
    @patch(f"{MODULE}.get_user_available_scopes", new_callable=AsyncMock, return_value=[])
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_authenticated(self, mock_get_user, mock_scopes, mock_pat_svc):
        from auth.api.routes.auth.tokens import tokens_page

        user = make_user()
        mock_get_user.return_value = user

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>tokens</html>")

        pat_service = AsyncMock()
        pat_service.list_user_tokens = AsyncMock(return_value=([], 0))
        mock_pat_svc.return_value = pat_service

        request = _mock_request()
        db = AsyncMock()

        with (
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
            patch(f"{MODULE}.get_user_admin_permissions", return_value={}),
            patch(
                f"{MODULE}.role_service.list_user_roles_with_scopes",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await tokens_page(request, db, branding_service)

        branding_service.render_template.assert_awaited_once()
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["is_admin"] is False
        assert ctx["active_section"] == "tokens"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated_redirects(self, mock_get_user, _pfx):
        from auth.api.routes.auth.tokens import tokens_page

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(
            headers={"host": "auth.example.com"},
            url_path="/auth/settings/tokens",
        )
        db = AsyncMock()

        result = await tokens_page(request, db, branding_service)

        assert result.status_code == 302
        location = result.headers.get("location", "")
        assert "/auth/login" in location

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated_with_query(self, mock_get_user, _pfx):
        from auth.api.routes.auth.tokens import tokens_page

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(
            headers={"host": "auth.example.com"},
            url_path="/auth/settings/tokens",
            query="tab=active",
        )
        db = AsyncMock()

        result = await tokens_page(request, db, branding_service)

        location = result.headers.get("location", "")
        assert "tab=active" in location


# ---------------------------------------------------------------------------
# list_tokens
# ---------------------------------------------------------------------------


class TestListTokens:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.auth.tokens import list_tokens

        user = make_user()
        mock_get_user.return_value = user

        pat = _make_pat()
        pat_service = AsyncMock()
        pat_service.list_user_tokens = AsyncMock(return_value=([pat], 1))

        request = _mock_request()
        db = AsyncMock()

        result = await list_tokens(
            request, db, pat_service, offset=0, limit=20, include_revoked=False
        )

        assert result.status_code == 200

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated(self, mock_get_user):
        from auth.api.routes.auth.tokens import list_tokens

        pat_service = AsyncMock()
        request = _mock_request()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await list_tokens(request, db, pat_service)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# create_token
# ---------------------------------------------------------------------------


class TestCreateToken:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_user_available_scopes", new_callable=AsyncMock)
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_success(self, mock_get_user, mock_scopes):
        from auth.api.routes.auth.tokens import create_token
        from auth.api.schemas.pat import CreatePATRequest

        user = make_user()
        mock_get_user.return_value = user
        mock_scopes.return_value = {
            "User": {"Profile": [("read:profile", "Read profile")]},
        }

        new_pat = _make_pat()
        pat_service = AsyncMock()
        pat_service.create_token = AsyncMock(return_value=(new_pat, "pat_plaintoken123"))

        data = CreatePATRequest(name="Test Token", scopes=["read:profile"], expiration="90_days")

        request = _mock_request()
        db = AsyncMock()

        result = await create_token(request, db, pat_service, data)

        assert result.status_code == 201
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated(self, mock_get_user):
        from auth.api.routes.auth.tokens import create_token
        from auth.api.schemas.pat import CreatePATRequest

        pat_service = AsyncMock()
        data = CreatePATRequest(name="Test", scopes=["read:profile"], expiration="90_days")

        with pytest.raises(HTTPException) as exc:
            await create_token(_mock_request(), AsyncMock(), pat_service, data)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_user_available_scopes", new_callable=AsyncMock)
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_unavailable_scope(self, mock_get_user, mock_scopes):
        from auth.api.routes.auth.tokens import create_token
        from auth.api.schemas.pat import CreatePATRequest

        user = make_user()
        mock_get_user.return_value = user
        mock_scopes.return_value = {
            "User": {"Profile": [("read:profile", "Read profile")]},
        }

        data = CreatePATRequest(name="Test", scopes=["admin:all"], expiration="90_days")

        with pytest.raises(HTTPException) as exc:
            await create_token(_mock_request(), AsyncMock(), AsyncMock(), data)
        assert exc.value.status_code == 400
        assert "not available" in exc.value.detail


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------


class TestGetToken:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.auth.tokens import get_token

        user = make_user()
        mock_get_user.return_value = user

        pat = _make_pat()
        pat_service = AsyncMock()
        pat_service.get_token_by_id = AsyncMock(return_value=pat)

        result = await get_token(str(pat.id), _mock_request(), AsyncMock(), pat_service)

        assert result.status_code == 200

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated(self, mock_get_user):
        from auth.api.routes.auth.tokens import get_token

        with pytest.raises(HTTPException) as exc:
            await get_token(str(uuid.uuid4()), _mock_request(), AsyncMock(), AsyncMock())
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_invalid_uuid(self, mock_get_user):
        from auth.api.routes.auth.tokens import get_token

        mock_get_user.return_value = make_user()

        with pytest.raises(HTTPException) as exc:
            await get_token("not-a-uuid", _mock_request(), AsyncMock(), AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_not_found(self, mock_get_user):
        from auth.api.routes.auth.tokens import get_token

        mock_get_user.return_value = make_user()
        pat_service = AsyncMock()
        pat_service.get_token_by_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await get_token(str(uuid.uuid4()), _mock_request(), AsyncMock(), pat_service)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# revoke_token
# ---------------------------------------------------------------------------


class TestRevokeToken:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_token

        user = make_user()
        mock_get_user.return_value = user
        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=True)
        db = AsyncMock()

        result = await revoke_token(str(uuid.uuid4()), _mock_request(), db, pat_service)

        assert result.status_code == 200
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_with_reason(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_token
        from auth.api.schemas.pat import RevokePATRequest

        user = make_user()
        mock_get_user.return_value = user
        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=True)
        db = AsyncMock()

        data = RevokePATRequest(reason="compromised")
        await revoke_token(str(uuid.uuid4()), _mock_request(), db, pat_service, data=data)

        call_kwargs = pat_service.revoke_token.call_args
        assert call_kwargs[1]["reason"] == "compromised"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_token

        with pytest.raises(HTTPException) as exc:
            await revoke_token(str(uuid.uuid4()), _mock_request(), AsyncMock(), AsyncMock())
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_invalid_uuid(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_token

        mock_get_user.return_value = make_user()

        with pytest.raises(HTTPException) as exc:
            await revoke_token("bad", _mock_request(), AsyncMock(), AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_not_found(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_token

        mock_get_user.return_value = make_user()
        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc:
            await revoke_token(str(uuid.uuid4()), _mock_request(), AsyncMock(), pat_service)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# regenerate_token
# ---------------------------------------------------------------------------


class TestRegenerateToken:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.auth.tokens import regenerate_token

        user = make_user()
        mock_get_user.return_value = user
        new_pat = _make_pat()
        pat_service = AsyncMock()
        pat_service.regenerate_token = AsyncMock(return_value=(new_pat, "new_plain_token"))
        db = AsyncMock()

        result = await regenerate_token(str(uuid.uuid4()), _mock_request(), db, pat_service)

        assert result.status_code == 201
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated(self, mock_get_user):
        from auth.api.routes.auth.tokens import regenerate_token

        with pytest.raises(HTTPException) as exc:
            await regenerate_token(str(uuid.uuid4()), _mock_request(), AsyncMock(), AsyncMock())
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_invalid_uuid(self, mock_get_user):
        from auth.api.routes.auth.tokens import regenerate_token

        mock_get_user.return_value = make_user()

        with pytest.raises(HTTPException) as exc:
            await regenerate_token("bad-uuid", _mock_request(), AsyncMock(), AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_not_found(self, mock_get_user):
        from auth.api.routes.auth.tokens import regenerate_token

        mock_get_user.return_value = make_user()
        pat_service = AsyncMock()
        pat_service.regenerate_token = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await regenerate_token(str(uuid.uuid4()), _mock_request(), AsyncMock(), pat_service)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# revoke_all_tokens
# ---------------------------------------------------------------------------


class TestRevokeAllTokens:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_all_tokens

        user = make_user()
        mock_get_user.return_value = user
        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=5)
        db = AsyncMock()

        result = await revoke_all_tokens(_mock_request(), db, pat_service)

        assert result.status_code == 200
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_with_reason(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_all_tokens

        user = make_user()
        mock_get_user.return_value = user
        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=3)
        db = AsyncMock()

        await revoke_all_tokens(_mock_request(), db, pat_service, reason="security audit")

        call_kwargs = pat_service.bulk_revoke.call_args
        assert call_kwargs[1]["reason"] == "security audit"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_all_tokens

        with pytest.raises(HTTPException) as exc:
            await revoke_all_tokens(_mock_request(), AsyncMock(), AsyncMock())
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_default_reason(self, mock_get_user):
        from auth.api.routes.auth.tokens import revoke_all_tokens

        user = make_user()
        mock_get_user.return_value = user
        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=0)
        db = AsyncMock()

        await revoke_all_tokens(_mock_request(), db, pat_service, reason=None)

        call_kwargs = pat_service.bulk_revoke.call_args
        assert "User requested" in call_kwargs[1]["reason"]


class TestGetCurrentTenantIdHelper:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.tokens import get_current_tenant_id

        assert get_current_tenant_id() is None

    @patch(f"{MODULE}.get_tenant_context")
    def test_with_context(self, mock_ctx):
        from auth.api.routes.auth.tokens import get_current_tenant_id

        mock_ctx.return_value = MagicMock(tenant_id="t-1")

        assert get_current_tenant_id() == "t-1"


class TestUpdateTokenScopes:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_not_authenticated(self, mock_get_user):
        from auth.api.routes.auth.tokens import update_token_scopes
        from auth.api.schemas.pat import UpdatePATScopesRequest

        with pytest.raises(HTTPException) as exc:
            await update_token_scopes(
                str(uuid.uuid4()),
                _mock_request(),
                AsyncMock(),
                AsyncMock(),
                UpdatePATScopesRequest(scopes=["read:profile"]),
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_invalid_uuid(self, mock_get_user):
        from auth.api.routes.auth.tokens import update_token_scopes
        from auth.api.schemas.pat import UpdatePATScopesRequest

        mock_get_user.return_value = make_user()

        with pytest.raises(HTTPException) as exc:
            await update_token_scopes(
                "not-a-uuid",
                _mock_request(),
                AsyncMock(),
                AsyncMock(),
                UpdatePATScopesRequest(scopes=["read:profile"]),
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_user_available_scopes", new_callable=AsyncMock)
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_unavailable_scope(self, mock_get_user, mock_scopes):
        from auth.api.routes.auth.tokens import update_token_scopes
        from auth.api.schemas.pat import UpdatePATScopesRequest

        mock_get_user.return_value = make_user()
        mock_scopes.return_value = {"User": {"Profile": [("read:profile", "Read profile")]}}

        with pytest.raises(HTTPException) as exc:
            await update_token_scopes(
                str(uuid.uuid4()),
                _mock_request(),
                AsyncMock(),
                AsyncMock(),
                UpdatePATScopesRequest(scopes=["admin:all"]),
            )
        assert exc.value.status_code == 400
        assert "not available" in exc.value.detail

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_user_available_scopes", new_callable=AsyncMock)
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_token_not_found(self, mock_get_user, mock_scopes):
        from auth.api.routes.auth.tokens import update_token_scopes
        from auth.api.schemas.pat import UpdatePATScopesRequest

        mock_get_user.return_value = make_user()
        mock_scopes.return_value = {"User": {"Profile": [("read:profile", "Read profile")]}}
        pat_service = AsyncMock()
        pat_service.update_token_scopes = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await update_token_scopes(
                str(uuid.uuid4()),
                _mock_request(),
                AsyncMock(),
                pat_service,
                UpdatePATScopesRequest(scopes=["read:profile"]),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_user_available_scopes", new_callable=AsyncMock)
    @patch(f"{MODULE}.get_current_user", new_callable=AsyncMock)
    async def test_success(self, mock_get_user, mock_scopes):
        from auth.api.routes.auth.tokens import update_token_scopes
        from auth.api.schemas.pat import UpdatePATScopesRequest

        mock_get_user.return_value = make_user()
        mock_scopes.return_value = {"User": {"Profile": [("read:profile", "Read profile")]}}
        pat_service = AsyncMock()
        pat_service.update_token_scopes = AsyncMock(return_value=_make_pat())
        db = AsyncMock()

        result = await update_token_scopes(
            str(uuid.uuid4()),
            _mock_request(),
            db,
            pat_service,
            UpdatePATScopesRequest(scopes=["read:profile"]),
        )

        assert result.status_code == 200
        db.commit.assert_awaited_once()
