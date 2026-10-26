# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for admin HTML page routes: jwks_pages, sessions_pages, scopes_pages, pats_pages."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import (
    make_jwk,
    make_personal_access_token,
    make_session,
    make_user,
)

# Module paths for patching
JWKS_PAGES_MODULE = "auth.api.routes.admin.jwks_pages"
SESSIONS_PAGES_MODULE = "auth.api.routes.admin.sessions_pages"
SCOPES_PAGES_MODULE = "auth.api.routes.admin.scopes_pages"
PATS_PAGES_MODULE = "auth.api.routes.admin.pats_pages"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_auth():
    """Create a standard (user, roles) auth tuple."""
    user = make_user()
    roles = [MagicMock()]
    return (user, roles)


def _make_request(query_params=None):
    """Create a mock Request with optional query_params."""
    request = MagicMock()
    request.query_params = query_params or {}
    return request


def _mock_templates():
    """Create a mock templates object whose TemplateResponse returns a mock."""
    templates = MagicMock()
    templates.TemplateResponse.return_value = MagicMock()
    return templates


def _mock_permissions():
    """Create a mock permissions dict."""
    return {"can_view": True, "can_edit": True}


def _make_scope_model(
    scope_id=None,
    name="users:read",
    description="Read users",
    resource="users",
    action="read",
    category="admin",
    is_system=False,
    is_active=True,
):
    """Create a mock Scope model."""
    scope = MagicMock()
    scope.id = scope_id or uuid.uuid4()
    scope.name = name
    scope.description = description
    scope.resource = resource
    scope.action = action
    scope.category = category
    scope.is_system = is_system
    scope.is_active = is_active
    scope.created_at = datetime.now(UTC)
    scope.updated_at = datetime.now(UTC)
    return scope


# ===========================================================================
# JWKS PAGES TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# jwk_to_dict
# ---------------------------------------------------------------------------


class TestJwkToDict:
    def test_basic_conversion(self):
        from auth.api.routes.admin.jwks_pages import jwk_to_dict

        jwk = make_jwk(kid="key-123", is_active=True)
        jwks_service = MagicMock()
        jwks_service.to_jwk_public.return_value = {"kty": "RSA", "kid": "key-123"}

        result = jwk_to_dict(jwk, jwks_service)

        assert result["kid"] == "key-123"
        assert result["kty"] == "RSA"
        assert result["alg"] == "RS256"
        assert result["use"] == "sig"
        assert result["is_active"] is True
        assert result["revoked_at"] is None
        assert result["created_at"] is not None
        assert result["public_key"] == {"kty": "RSA", "kid": "key-123"}
        jwks_service.to_jwk_public.assert_called_once_with(jwk)

    def test_with_revoked_at(self):
        from auth.api.routes.admin.jwks_pages import jwk_to_dict

        revoked_time = datetime(2025, 3, 15, 12, 0, 0, tzinfo=UTC)
        jwk = make_jwk(kid="rev-key", is_active=False, revoked_at=revoked_time)
        jwks_service = MagicMock()
        jwks_service.to_jwk_public.return_value = {"kty": "RSA"}

        result = jwk_to_dict(jwk, jwks_service)

        assert result["is_active"] is False
        assert result["revoked_at"] == "2025-03-15T12:00:00+00:00"

    def test_timestamps_none(self):
        from auth.api.routes.admin.jwks_pages import jwk_to_dict

        jwk = make_jwk()
        jwk.created_at = None
        jwk.revoked_at = None
        jwks_service = MagicMock()
        jwks_service.to_jwk_public.return_value = {}

        result = jwk_to_dict(jwk, jwks_service)

        assert result["created_at"] is None
        assert result["revoked_at"] is None


# ---------------------------------------------------------------------------
# jwks_list_page
# ---------------------------------------------------------------------------


class TestJwksListPage:
    async def test_renders_empty_list(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_list_page

        request = _make_request()
        auth = _make_auth()
        jwks_service = MagicMock()
        jwks_service.list = AsyncMock(return_value=[])

        mock_templates = _mock_templates()

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await jwks_list_page(request=request, db=db, jwks_service=jwks_service, auth=auth)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "jwks"
        assert ctx["keys"] == []
        assert ctx["success"] is None
        assert ctx["error"] is None

    async def test_renders_keys(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_list_page

        jwk1 = make_jwk(kid="k1")
        jwk2 = make_jwk(kid="k2")
        request = _make_request()
        auth = _make_auth()

        jwks_service = MagicMock()
        jwks_service.list = AsyncMock(return_value=[jwk1, jwk2])
        jwks_service.to_jwk_public = MagicMock(return_value={"kty": "RSA"})

        mock_templates = _mock_templates()

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await jwks_list_page(request=request, db=db, jwks_service=jwks_service, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert len(ctx["keys"]) == 2
        assert ctx["keys"][0]["kid"] == "k1"
        assert ctx["keys"][1]["kid"] == "k2"

    async def test_reads_success_and_error_from_query_params(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_list_page

        request = _make_request({"success": "done", "error": "oops"})
        auth = _make_auth()

        jwks_service = MagicMock()
        jwks_service.list = AsyncMock(return_value=[])

        mock_templates = _mock_templates()

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await jwks_list_page(request=request, db=db, jwks_service=jwks_service, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["success"] == "done"
        assert ctx["error"] == "oops"

    async def test_passes_current_user_and_permissions(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_list_page

        request = _make_request()
        auth = _make_auth()
        user, roles = auth

        jwks_service = MagicMock()
        jwks_service.list = AsyncMock(return_value=[])

        mock_templates = _mock_templates()
        perms = {"can_manage_jwks": True}

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=perms,
            ),
        ):
            await jwks_list_page(request=request, db=db, jwks_service=jwks_service, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["current_user"] is user
        assert ctx["permissions"] == perms


# ---------------------------------------------------------------------------
# jwks_generate_page
# ---------------------------------------------------------------------------


class TestJwksGeneratePage:
    async def test_renders_form(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_generate_page

        request = _make_request()
        auth = _make_auth()
        mock_templates = _mock_templates()

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await jwks_generate_page(request=request, auth=auth)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "jwks"

    async def test_reads_error_from_query(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_generate_page

        request = _make_request({"error": "something went wrong"})
        auth = _make_auth()
        mock_templates = _mock_templates()

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await jwks_generate_page(request=request, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["error"] == "something went wrong"


# ---------------------------------------------------------------------------
# jwks_generate_submit
# ---------------------------------------------------------------------------


class TestJwksGenerateSubmit:
    async def test_valid_key_size_2048(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_generate_submit

        jwk = make_jwk(kid="new-key")
        jwks_service = MagicMock()
        jwks_service.generate_key = AsyncMock(return_value=jwk)
        auth = _make_auth()
        request = _make_request()

        result = await jwks_generate_submit(
            request=request,
            db=db,
            jwks_service=jwks_service,
            auth=auth,
            key_size=2048,
            activate=None,
        )

        assert result.status_code == 303
        assert f"/admin/jwks/{jwk.kid}" in result.headers["location"]
        jwks_service.generate_key.assert_awaited_once_with(db, key_size=2048, activate=False)

    async def test_valid_key_size_4096_with_activate(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_generate_submit

        jwk = make_jwk(kid="big-key")
        jwks_service = MagicMock()
        jwks_service.generate_key = AsyncMock(return_value=jwk)
        auth = _make_auth()
        request = _make_request()

        result = await jwks_generate_submit(
            request=request,
            db=db,
            jwks_service=jwks_service,
            auth=auth,
            key_size=4096,
            activate="true",
        )

        assert result.status_code == 303
        jwks_service.generate_key.assert_awaited_once_with(db, key_size=4096, activate=True)

    async def test_valid_key_size_3072(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_generate_submit

        jwk = make_jwk(kid="mid-key")
        jwks_service = MagicMock()
        jwks_service.generate_key = AsyncMock(return_value=jwk)
        auth = _make_auth()
        request = _make_request()

        result = await jwks_generate_submit(
            request=request,
            db=db,
            jwks_service=jwks_service,
            auth=auth,
            key_size=3072,
            activate=None,
        )

        assert result.status_code == 303

    async def test_invalid_key_size(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_generate_submit

        jwks_service = MagicMock()
        auth = _make_auth()
        request = _make_request()

        result = await jwks_generate_submit(
            request=request,
            db=db,
            jwks_service=jwks_service,
            auth=auth,
            key_size=1024,
            activate=None,
        )

        assert result.status_code == 303
        assert "error=Invalid" in result.headers["location"]

    async def test_service_error(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_generate_submit

        jwks_service = MagicMock()
        jwks_service.generate_key = AsyncMock(side_effect=RuntimeError("gen failed"))
        auth = _make_auth()
        request = _make_request()

        result = await jwks_generate_submit(
            request=request,
            db=db,
            jwks_service=jwks_service,
            auth=auth,
            key_size=2048,
            activate=None,
        )

        assert result.status_code == 303
        assert "error=" in result.headers["location"]


# ---------------------------------------------------------------------------
# jwks_detail_page
# ---------------------------------------------------------------------------


class TestJwksDetailPage:
    async def test_key_found(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_detail_page

        jwk = make_jwk(kid="my-kid")
        jwks_service = MagicMock()
        jwks_service.get_by_kid = AsyncMock(return_value=jwk)
        jwks_service.to_jwk_public = MagicMock(return_value={"kty": "RSA", "kid": "my-kid"})

        request = _make_request()
        auth = _make_auth()
        mock_templates = _mock_templates()

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await jwks_detail_page(
                request=request,
                kid="my-kid",
                db=db,
                jwks_service=jwks_service,
                auth=auth,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "jwks"
        assert ctx["key"]["kid"] == "my-kid"
        assert '"kty"' in ctx["public_key_json"]

    async def test_key_not_found(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_detail_page

        jwks_service = MagicMock()
        jwks_service.get_by_kid = AsyncMock(return_value=None)
        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc:
            await jwks_detail_page(
                request=request,
                kid="unknown",
                db=db,
                jwks_service=jwks_service,
                auth=auth,
            )

        assert exc.value.status_code == 404
        assert "Key not found" in exc.value.detail

    async def test_reads_query_params(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_detail_page

        jwk = make_jwk(kid="detail-key")
        jwks_service = MagicMock()
        jwks_service.get_by_kid = AsyncMock(return_value=jwk)
        jwks_service.to_jwk_public = MagicMock(return_value={})

        request = _make_request({"success": "activated", "error": "nope"})
        auth = _make_auth()
        mock_templates = _mock_templates()

        with (
            patch(f"{JWKS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{JWKS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await jwks_detail_page(
                request=request,
                kid="detail-key",
                db=db,
                jwks_service=jwks_service,
                auth=auth,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["success"] == "activated"
        assert ctx["error"] == "nope"


# ---------------------------------------------------------------------------
# jwks_activate_submit
# ---------------------------------------------------------------------------


class TestJwksActivateSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_activate_submit

        jwk = make_jwk(kid="act-key")
        jwks_service = MagicMock()
        jwks_service.activate_key = AsyncMock(return_value=jwk)
        auth = _make_auth()

        result = await jwks_activate_submit(
            kid="act-key", db=db, jwks_service=jwks_service, auth=auth
        )

        assert result.status_code == 303
        assert "/admin/jwks/act-key" in result.headers["location"]
        assert "success=" in result.headers["location"]

    async def test_key_not_found(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_activate_submit

        jwks_service = MagicMock()
        jwks_service.activate_key = AsyncMock(return_value=None)
        auth = _make_auth()

        result = await jwks_activate_submit(
            kid="missing", db=db, jwks_service=jwks_service, auth=auth
        )

        assert result.status_code == 303
        assert "error=Key+not+found" in result.headers["location"]

    async def test_value_error(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_activate_submit

        jwks_service = MagicMock()
        jwks_service.activate_key = AsyncMock(side_effect=ValueError("Cannot activate revoked key"))
        auth = _make_auth()

        result = await jwks_activate_submit(
            kid="bad-key", db=db, jwks_service=jwks_service, auth=auth
        )

        assert result.status_code == 303
        assert "error=" in result.headers["location"]


# ---------------------------------------------------------------------------
# jwks_revoke_submit
# ---------------------------------------------------------------------------


class TestJwksRevokeSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_revoke_submit

        jwk = make_jwk(kid="rev-key")
        jwks_service = MagicMock()
        jwks_service.revoke_key = AsyncMock(return_value=jwk)
        auth = _make_auth()

        result = await jwks_revoke_submit(
            kid="rev-key", db=db, jwks_service=jwks_service, auth=auth
        )

        assert result.status_code == 303
        assert "/admin/jwks/rev-key" in result.headers["location"]
        assert "success=" in result.headers["location"]

    async def test_key_not_found(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_revoke_submit

        jwks_service = MagicMock()
        jwks_service.revoke_key = AsyncMock(return_value=None)
        auth = _make_auth()

        result = await jwks_revoke_submit(
            kid="missing", db=db, jwks_service=jwks_service, auth=auth
        )

        assert result.status_code == 303
        assert "error=Key+not+found" in result.headers["location"]


# ---------------------------------------------------------------------------
# jwks_delete_submit
# ---------------------------------------------------------------------------


class TestJwksDeleteSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_delete_submit

        jwks_service = MagicMock()
        jwks_service.delete = AsyncMock(return_value=True)
        auth = _make_auth()

        result = await jwks_delete_submit(
            kid="del-key", db=db, jwks_service=jwks_service, auth=auth
        )

        assert result.status_code == 303
        assert "/admin/jwks?" in result.headers["location"]
        assert "success=" in result.headers["location"]

    async def test_not_found_or_not_revoked(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_delete_submit

        jwks_service = MagicMock()
        jwks_service.delete = AsyncMock(return_value=False)
        auth = _make_auth()

        result = await jwks_delete_submit(
            kid="bad-key", db=db, jwks_service=jwks_service, auth=auth
        )

        assert result.status_code == 303
        assert "error=" in result.headers["location"]


# ---------------------------------------------------------------------------
# jwks_rotate_submit
# ---------------------------------------------------------------------------


class TestJwksRotateSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_rotate_submit

        jwk = make_jwk(kid="rot-key")
        jwks_service = MagicMock()
        jwks_service.rotate_keys = AsyncMock(return_value=jwk)
        auth = _make_auth()

        result = await jwks_rotate_submit(db=db, jwks_service=jwks_service, auth=auth)

        assert result.status_code == 303
        assert f"/admin/jwks/{jwk.kid}" in result.headers["location"]
        assert "success=" in result.headers["location"]

    async def test_service_error(self, db):
        from auth.api.routes.admin.jwks_pages import jwks_rotate_submit

        jwks_service = MagicMock()
        jwks_service.rotate_keys = AsyncMock(side_effect=RuntimeError("rotation failed"))
        auth = _make_auth()

        result = await jwks_rotate_submit(db=db, jwks_service=jwks_service, auth=auth)

        assert result.status_code == 303
        assert "error=" in result.headers["location"]


# ===========================================================================
# SESSIONS PAGES TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# parse_user_agent
# ---------------------------------------------------------------------------


class TestParseUserAgent:
    def test_none_input(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        result = parse_user_agent(None)
        assert result == {"browser": "Unknown", "os": "Unknown"}

    def test_empty_string(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        result = parse_user_agent("")
        assert result == {"browser": "Unknown", "os": "Unknown"}

    def test_chrome_windows(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        result = parse_user_agent(ua)
        assert result["browser"] == "Chrome"
        assert result["os"] == "Windows"

    def test_firefox_linux(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0"
        result = parse_user_agent(ua)
        assert result["browser"] == "Firefox"
        assert result["os"] == "Linux"

    def test_safari_macos(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        result = parse_user_agent(ua)
        assert result["browser"] == "Safari"
        assert result["os"] == "macOS"

    def test_edge_windows(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        result = parse_user_agent(ua)
        assert result["browser"] == "Edge"
        assert result["os"] == "Windows"

    def test_opera_opr(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        # The code checks "Chrome" before "Opera"/"OPR", so Chrome wins when both present.
        # The OPR substring alone triggers Opera detection.
        ua = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 OPR/106.0.0.0"
        result = parse_user_agent(ua)
        assert result["browser"] == "Opera"
        assert result["os"] == "Windows"

    def test_opera_keyword(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "Opera/9.80 (Windows NT 6.1) Presto/2.12.388"
        result = parse_user_agent(ua)
        assert result["browser"] == "Opera"

    def test_chrome_beats_opr_when_both_present(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        # Real Opera UA has Chrome+OPR. Code checks Chrome first (before Opera/OPR),
        # but then also checks "Edg" absence. Since "Edg" is absent, Chrome matches first.
        ua = "Mozilla/5.0 Chrome/120.0 OPR/106.0"
        result = parse_user_agent(ua)
        # Chrome is detected because it's checked before Opera in the code
        assert result["browser"] == "Chrome"

    def test_android(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
        result = parse_user_agent(ua)
        # Android has "Linux" in it but Android check is after Linux in the code
        # Actually "Linux" comes before "Android" in the OS detection, so it returns Linux
        # Let me check: the code checks "Linux" before "Android"
        # So for "Linux; Android 14" -> os = "Linux" (Linux is checked first)
        assert result["os"] == "Linux"

    def test_android_only(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "Mozilla/5.0 (Android 14) AppleWebKit/537.36 Chrome/120.0.0.0"
        result = parse_user_agent(ua)
        assert result["os"] == "Android"

    def test_ios_keyword_only(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        # Use a UA with "iOS" but NOT "Mac OS" or "Macintosh" to avoid macOS detection
        ua = "Mozilla/5.0 (iOS 17_0) AppleWebKit/605.1.15"
        result = parse_user_agent(ua)
        assert result["os"] == "iOS"

    def test_iphone_without_mac_os(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        # "iPhone" only, no "Mac OS" substring
        ua = "Mozilla/5.0 (iPhone; CPU) AppleWebKit/605.1.15"
        result = parse_user_agent(ua)
        assert result["os"] == "iOS"

    def test_ipad_without_mac_os(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        # "iPad" only, no "Mac OS" substring
        ua = "Mozilla/5.0 (iPad; CPU) AppleWebKit/605.1.15"
        result = parse_user_agent(ua)
        assert result["os"] == "iOS"

    def test_macos_beats_iphone_when_both_present(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        # Real iPhone UA has "like Mac OS X", so macOS detection triggers first
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
        result = parse_user_agent(ua)
        assert result["os"] == "macOS"

    def test_unknown_browser_and_os(self):
        from auth.api.routes.admin.sessions_pages import parse_user_agent

        ua = "SomeBotCrawler/1.0"
        result = parse_user_agent(ua)
        assert result["browser"] == "Unknown"
        assert result["os"] == "Unknown"


# ---------------------------------------------------------------------------
# session_to_dict
# ---------------------------------------------------------------------------


class TestSessionToDict:
    def test_active_session(self):
        from auth.api.routes.admin.sessions_pages import session_to_dict

        session = make_session()
        result = session_to_dict(session, "user@example.com")

        assert result["id"] == str(session.id)
        assert result["user_id"] == str(session.user_id)
        assert result["user_email"] == "user@example.com"
        assert result["ip_address"] == "127.0.0.1"
        assert result["user_agent"] == "TestAgent/1.0"
        assert result["is_active"] is True
        assert result["created_at"] is not None
        assert result["expires_at"] is not None
        assert result["revoked_at"] is None

    def test_revoked_session(self):
        from auth.api.routes.admin.sessions_pages import session_to_dict

        revoked_time = datetime.now(UTC)
        session = make_session(revoked_at=revoked_time)
        result = session_to_dict(session)

        assert result["is_active"] is False
        assert result["revoked_at"] is not None

    def test_expired_session(self):
        from auth.api.routes.admin.sessions_pages import session_to_dict

        session = make_session(expires_at=datetime.now(UTC) - timedelta(hours=1))
        result = session_to_dict(session)

        assert result["is_active"] is False

    def test_no_email(self):
        from auth.api.routes.admin.sessions_pages import session_to_dict

        session = make_session()
        result = session_to_dict(session)

        assert result["user_email"] is None

    def test_created_at_none(self):
        from auth.api.routes.admin.sessions_pages import session_to_dict

        session = make_session()
        session.created_at = None
        # Keep expires_at valid since `expires_at > now` comparison requires a datetime
        result = session_to_dict(session)
        assert result["created_at"] is None
        assert result["expires_at"] is not None


# ---------------------------------------------------------------------------
# sessions_list_page
# ---------------------------------------------------------------------------


class TestSessionsListPage:
    async def test_renders_empty_list(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_list_page

        request = _make_request()
        auth = _make_auth()

        # count query returns 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        # sessions query returns empty list
        sessions_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        sessions_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[count_result, sessions_result])

        mock_templates = _mock_templates()

        with (
            patch(f"{SESSIONS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SESSIONS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await sessions_list_page(request=request, db=db, auth=auth, page=1, active_only=True)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "sessions"
        assert ctx["sessions"] == []
        assert ctx["total"] == 0
        assert ctx["page"] == 1

    async def test_renders_with_sessions(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_list_page

        session1 = make_session()
        # Attach a user with a primary email so the page can resolve user_email
        email_obj = MagicMock()
        email_obj.email = "test@example.com"
        email_obj.is_primary = True
        mock_user = MagicMock()
        mock_user.emails = [email_obj]
        session1.user = mock_user

        request = _make_request()
        auth = _make_auth()

        mock_templates = _mock_templates()

        with (
            patch(
                f"{SESSIONS_PAGES_MODULE}._session_repo.list",
                new_callable=AsyncMock,
                return_value=([session1], 1),
            ),
            patch(f"{SESSIONS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SESSIONS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await sessions_list_page(request=request, db=db, auth=auth, page=1, active_only=True)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert len(ctx["sessions"]) == 1
        assert ctx["sessions"][0]["user_email"] == "test@example.com"
        assert "parsed_ua" in ctx["sessions"][0]

    async def test_pagination_calculation(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_list_page

        request = _make_request()
        auth = _make_auth()

        count_result = MagicMock()
        count_result.scalar.return_value = 45

        sessions_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        sessions_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[count_result, sessions_result])

        mock_templates = _mock_templates()

        with (
            patch(f"{SESSIONS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SESSIONS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await sessions_list_page(request=request, db=db, auth=auth, page=2, active_only=True)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["total"] == 45
        assert ctx["page"] == 2
        assert ctx["total_pages"] == 3  # ceil(45/20)

    async def test_count_none_defaults_to_zero(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_list_page

        request = _make_request()
        auth = _make_auth()

        count_result = MagicMock()
        count_result.scalar.return_value = None

        sessions_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        sessions_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[count_result, sessions_result])

        mock_templates = _mock_templates()

        with (
            patch(f"{SESSIONS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SESSIONS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await sessions_list_page(request=request, db=db, auth=auth, page=1, active_only=True)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["total"] == 0


# ---------------------------------------------------------------------------
# session_detail_page
# ---------------------------------------------------------------------------


class TestSessionDetailPage:
    async def test_valid_session(self, db):
        from auth.api.routes.admin.sessions_pages import session_detail_page

        session = make_session()
        session_id = str(session.id)

        email_obj = MagicMock()
        email_obj.email = "user@test.com"
        email_obj.is_primary = True
        mock_user = MagicMock()
        mock_user.emails = [email_obj]
        session.user = mock_user

        request = _make_request()
        auth = _make_auth()
        mock_templates = _mock_templates()

        with (
            patch(
                f"{SESSIONS_PAGES_MODULE}._session_repo.find_by_id_with_user",
                new_callable=AsyncMock,
                return_value=session,
            ),
            patch(f"{SESSIONS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SESSIONS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await session_detail_page(request=request, session_id=session_id, db=db, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "sessions"
        assert ctx["session"]["id"] == session_id
        assert ctx["session"]["user_email"] == "user@test.com"

    async def test_invalid_session_id_format(self, db):
        from auth.api.routes.admin.sessions_pages import session_detail_page

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc:
            await session_detail_page(request=request, session_id="not-a-uuid", db=db, auth=auth)

        assert exc.value.status_code == 400
        assert "Invalid session ID format" in exc.value.detail

    async def test_session_not_found(self, db):
        from auth.api.routes.admin.sessions_pages import session_detail_page

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc:
            await session_detail_page(
                request=request, session_id=str(uuid.uuid4()), db=db, auth=auth
            )

        assert exc.value.status_code == 404
        assert "Session not found" in exc.value.detail


# ---------------------------------------------------------------------------
# session_revoke_submit
# ---------------------------------------------------------------------------


class TestSessionRevokeSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.sessions_pages import session_revoke_submit

        session = make_session()
        session.revoked_at = None
        session_id = str(session.id)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = session
        db.execute = AsyncMock(return_value=result_mock)

        auth = _make_auth()

        result = await session_revoke_submit(session_id=session_id, db=db, auth=auth)

        assert result.status_code == 303
        assert "success=" in result.headers["location"]
        assert session.revoked_at is not None
        db.commit.assert_awaited_once()

    async def test_invalid_session_id(self, db):
        from auth.api.routes.admin.sessions_pages import session_revoke_submit

        auth = _make_auth()

        result = await session_revoke_submit(session_id="bad-id", db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Invalid" in result.headers["location"]

    async def test_session_not_found(self, db):
        from auth.api.routes.admin.sessions_pages import session_revoke_submit

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        auth = _make_auth()

        result = await session_revoke_submit(session_id=str(uuid.uuid4()), db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Session+not+found" in result.headers["location"]

    async def test_already_revoked(self, db):
        from auth.api.routes.admin.sessions_pages import session_revoke_submit

        session = make_session(revoked_at=datetime.now(UTC))
        session_id = str(session.id)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = session
        db.execute = AsyncMock(return_value=result_mock)

        auth = _make_auth()

        result = await session_revoke_submit(session_id=session_id, db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Session+already+revoked" in result.headers["location"]


# ---------------------------------------------------------------------------
# sessions_revoke_all_submit
# ---------------------------------------------------------------------------


class TestSessionsRevokeAllSubmit:
    async def test_revoke_all_no_user_filter(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_revoke_all_submit

        session1 = make_session()
        session1.revoked_at = None
        session2 = make_session()
        session2.revoked_at = None

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [session1, session2]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        auth = _make_auth()

        result = await sessions_revoke_all_submit(db=db, auth=auth, user_id=None)

        assert result.status_code == 303
        assert "success=Revoked+2" in result.headers["location"]
        db.commit.assert_awaited_once()

    async def test_revoke_all_with_user_filter(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_revoke_all_submit

        session1 = make_session()
        session1.revoked_at = None

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [session1]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        auth = _make_auth()
        user_id = str(uuid.uuid4())

        result = await sessions_revoke_all_submit(db=db, auth=auth, user_id=user_id)

        assert result.status_code == 303
        assert "success=Revoked+1" in result.headers["location"]

    async def test_revoke_all_invalid_user_id(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_revoke_all_submit

        auth = _make_auth()

        result = await sessions_revoke_all_submit(db=db, auth=auth, user_id="invalid-uuid")

        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers["location"]

    async def test_revoke_all_zero_sessions(self, db):
        from auth.api.routes.admin.sessions_pages import sessions_revoke_all_submit

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        auth = _make_auth()

        result = await sessions_revoke_all_submit(db=db, auth=auth, user_id=None)

        assert result.status_code == 303
        assert "success=Revoked+0" in result.headers["location"]


# ===========================================================================
# SCOPES PAGES TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# scope_to_dict
# ---------------------------------------------------------------------------


class TestScopeToDict:
    def test_basic_conversion(self):
        from auth.api.routes.admin.scopes_pages import scope_to_dict

        scope = _make_scope_model(name="users:read")
        result = scope_to_dict(scope, role_count=5)

        assert result["id"] == str(scope.id)
        assert result["name"] == "users:read"
        assert result["description"] == "Read users"
        assert result["resource"] == "users"
        assert result["action"] == "read"
        assert result["category"] == "admin"
        assert result["is_system"] is False
        assert result["is_active"] is True
        assert result["role_count"] == 5
        assert result["created_at"] is not None
        assert result["updated_at"] is not None

    def test_default_role_count_zero(self):
        from auth.api.routes.admin.scopes_pages import scope_to_dict

        scope = _make_scope_model()
        result = scope_to_dict(scope)

        assert result["role_count"] == 0

    def test_timestamps_none(self):
        from auth.api.routes.admin.scopes_pages import scope_to_dict

        scope = _make_scope_model()
        scope.created_at = None
        scope.updated_at = None
        result = scope_to_dict(scope)

        assert result["created_at"] is None
        assert result["updated_at"] is None

    def test_system_scope(self):
        from auth.api.routes.admin.scopes_pages import scope_to_dict

        scope = _make_scope_model(is_system=True, is_active=True)
        result = scope_to_dict(scope)

        assert result["is_system"] is True


# ---------------------------------------------------------------------------
# scopes_list_page
# ---------------------------------------------------------------------------


class TestScopesListPage:
    async def test_renders_empty_list(self, db):
        from auth.api.routes.admin.scopes_pages import scopes_list_page

        request = _make_request()
        auth = _make_auth()

        service = MagicMock()
        service.list = AsyncMock(return_value=([], 0))
        service.count_roles_for_scope = AsyncMock(return_value=0)
        service.list_distinct_categories = AsyncMock(return_value=[])

        mock_templates = _mock_templates()

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            patch(f"{SCOPES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SCOPES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await scopes_list_page(
                request=request,
                db=db,
                auth=auth,
                page=1,
                search=None,
                category=None,
                is_active=None,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "scopes"
        assert ctx["scopes"] == []
        assert ctx["total"] == 0

    async def test_renders_with_scopes(self, db):
        from auth.api.routes.admin.scopes_pages import scopes_list_page

        scope1 = _make_scope_model(name="users:read")

        request = _make_request()
        auth = _make_auth()

        service = MagicMock()
        service.list = AsyncMock(return_value=([scope1], 1))
        service.count_roles_for_scope = AsyncMock(return_value=3)
        service.list_distinct_categories = AsyncMock(return_value=["admin"])

        mock_templates = _mock_templates()

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            patch(f"{SCOPES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SCOPES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await scopes_list_page(
                request=request,
                db=db,
                auth=auth,
                page=1,
                search=None,
                category=None,
                is_active=None,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert len(ctx["scopes"]) == 1
        assert ctx["scopes"][0]["name"] == "users:read"
        assert ctx["scopes"][0]["role_count"] == 3

    async def test_pagination(self, db):
        from auth.api.routes.admin.scopes_pages import scopes_list_page

        request = _make_request()
        auth = _make_auth()

        service = MagicMock()
        service.list = AsyncMock(return_value=([], 45))
        service.count_roles_for_scope = AsyncMock(return_value=0)
        service.list_distinct_categories = AsyncMock(return_value=[])

        mock_templates = _mock_templates()

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            patch(f"{SCOPES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SCOPES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await scopes_list_page(
                request=request,
                db=db,
                auth=auth,
                page=2,
                search=None,
                category=None,
                is_active=None,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["total"] == 45
        assert ctx["total_pages"] == 3  # ceil(45/20)


# ---------------------------------------------------------------------------
# scope_create_page
# ---------------------------------------------------------------------------


class TestScopeCreatePage:
    async def test_renders_form(self, db):
        from auth.api.routes.admin.scopes_pages import scope_create_page

        request = _make_request()
        auth = _make_auth()
        mock_templates = _mock_templates()
        service = MagicMock()
        service.list_distinct_categories = AsyncMock(return_value=["api", "custom"])

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            patch(f"{SCOPES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SCOPES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await scope_create_page(request=request, db=db, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "scopes"
        assert ctx["categories"] == ["api", "custom"]

    async def test_reads_error_from_query(self, db):
        from auth.api.routes.admin.scopes_pages import scope_create_page

        request = _make_request({"error": "name taken"})
        auth = _make_auth()
        mock_templates = _mock_templates()
        service = MagicMock()
        service.list_distinct_categories = AsyncMock(return_value=[])

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            patch(f"{SCOPES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SCOPES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await scope_create_page(request=request, db=db, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["error"] == "name taken"


# ---------------------------------------------------------------------------
# scope_create_submit
# ---------------------------------------------------------------------------


class TestScopeCreateSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.scopes_pages import scope_create_submit

        scope_id = uuid.uuid4()

        async def mock_refresh(obj):
            obj.id = scope_id

        db.refresh = AsyncMock(side_effect=mock_refresh)

        service = MagicMock()
        service.name_exists = AsyncMock(return_value=False)
        service.stage = AsyncMock()

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_create_submit(
                db=db,
                auth=auth,
                name="custom:write",
                resource="custom",
                action="write",
                category="custom",
                description="Write custom",
            )

        assert result.status_code == 303
        assert f"/admin/scopes/{scope_id}" in result.headers["location"]
        assert "success=" in result.headers["location"]
        service.stage.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_name_already_exists(self, db):
        from auth.api.routes.admin.scopes_pages import scope_create_submit

        service = MagicMock()
        service.name_exists = AsyncMock(return_value=True)

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_create_submit(
                db=db,
                auth=auth,
                name="users:read",
                resource="users",
                action="read",
            )

        assert result.status_code == 303
        assert "error=Scope+name+already+exists" in result.headers["location"]

    async def test_exception_during_creation(self, db):
        from auth.api.routes.admin.scopes_pages import scope_create_submit

        service = MagicMock()
        service.name_exists = AsyncMock(return_value=False)
        service.stage = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db error"))

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_create_submit(
                db=db,
                auth=auth,
                name="new:scope",
                resource="new",
                action="scope",
            )

        assert result.status_code == 303
        assert "error=" in result.headers["location"]


# ---------------------------------------------------------------------------
# scope_detail_page
# ---------------------------------------------------------------------------


class TestScopeDetailPage:
    async def test_valid_scope(self, db):
        from auth.api.routes.admin.scopes_pages import scope_detail_page

        scope = _make_scope_model()
        scope_id = str(scope.id)

        role1 = MagicMock()
        role1.id = uuid.uuid4()
        role1.name = "admin"
        role1.description = "Admin role"
        role1.is_system = True

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=scope)
        service.list_roles_for_scope = AsyncMock(return_value=[role1])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _mock_templates()

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            patch(f"{SCOPES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{SCOPES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await scope_detail_page(request=request, scope_id=scope_id, db=db, auth=auth)

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "scopes"
        assert ctx["scope"]["name"] == "users:read"
        assert len(ctx["scope"]["roles"]) == 1
        assert ctx["scope"]["roles"][0]["name"] == "admin"

    async def test_invalid_scope_id(self, db):
        from auth.api.routes.admin.scopes_pages import scope_detail_page

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc:
            await scope_detail_page(request=request, scope_id="not-a-uuid", db=db, auth=auth)

        assert exc.value.status_code == 400

    async def test_scope_not_found(self, db):
        from auth.api.routes.admin.scopes_pages import scope_detail_page

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)

        request = _make_request()
        auth = _make_auth()

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            pytest.raises(HTTPException) as exc,
        ):
            await scope_detail_page(request=request, scope_id=str(uuid.uuid4()), db=db, auth=auth)

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# scope_toggle_submit
# ---------------------------------------------------------------------------


class TestScopeToggleSubmit:
    async def test_toggle_to_disabled(self, db):
        from auth.api.routes.admin.scopes_pages import scope_toggle_submit

        scope = _make_scope_model(is_active=True, is_system=False)
        scope_id = str(scope.id)

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=scope)

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_toggle_submit(scope_id=scope_id, db=db, auth=auth)

        assert result.status_code == 303
        assert scope.is_active is False
        assert "success=" in result.headers["location"]
        db.commit.assert_awaited_once()

    async def test_toggle_to_enabled(self, db):
        from auth.api.routes.admin.scopes_pages import scope_toggle_submit

        scope = _make_scope_model(is_active=False, is_system=False)
        scope_id = str(scope.id)

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=scope)

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_toggle_submit(scope_id=scope_id, db=db, auth=auth)

        assert result.status_code == 303
        assert scope.is_active is True

    async def test_invalid_scope_id(self, db):
        from auth.api.routes.admin.scopes_pages import scope_toggle_submit

        auth = _make_auth()

        result = await scope_toggle_submit(scope_id="bad-id", db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Invalid" in result.headers["location"]

    async def test_scope_not_found(self, db):
        from auth.api.routes.admin.scopes_pages import scope_toggle_submit

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_toggle_submit(scope_id=str(uuid.uuid4()), db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Scope+not+found" in result.headers["location"]

    async def test_system_scope_blocked(self, db):
        from auth.api.routes.admin.scopes_pages import scope_toggle_submit

        scope = _make_scope_model(is_system=True)
        scope_id = str(scope.id)

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=scope)

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_toggle_submit(scope_id=scope_id, db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Cannot+toggle+system+scopes" in result.headers["location"]


# ---------------------------------------------------------------------------
# scope_delete_submit
# ---------------------------------------------------------------------------


class TestScopeDeleteSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.scopes_pages import scope_delete_submit

        scope = _make_scope_model(is_system=False)
        scope_id = str(scope.id)

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=scope)
        service.delete = AsyncMock()

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_delete_submit(scope_id=scope_id, db=db, auth=auth)

        assert result.status_code == 303
        assert "success=Scope+deleted" in result.headers["location"]
        service.delete.assert_awaited_once_with(db, scope)
        db.commit.assert_awaited_once()

    async def test_invalid_scope_id(self, db):
        from auth.api.routes.admin.scopes_pages import scope_delete_submit

        auth = _make_auth()

        result = await scope_delete_submit(scope_id="bad-id", db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Invalid" in result.headers["location"]

    async def test_scope_not_found(self, db):
        from auth.api.routes.admin.scopes_pages import scope_delete_submit

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_delete_submit(scope_id=str(uuid.uuid4()), db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Scope+not+found" in result.headers["location"]

    async def test_system_scope_blocked(self, db):
        from auth.api.routes.admin.scopes_pages import scope_delete_submit

        scope = _make_scope_model(is_system=True)
        scope_id = str(scope.id)

        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=scope)

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await scope_delete_submit(scope_id=scope_id, db=db, auth=auth)

        assert result.status_code == 303
        assert "error=Cannot+delete+system+scopes" in result.headers["location"]


# ---------------------------------------------------------------------------
# seed_default_scopes_submit
# ---------------------------------------------------------------------------


class TestSeedDefaultScopesSubmit:
    async def test_seeds_new_scopes(self, db):
        from auth.api.routes.admin.scopes_pages import seed_default_scopes_submit

        service = MagicMock()
        service.name_exists = AsyncMock(return_value=False)
        service.stage = AsyncMock()

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await seed_default_scopes_submit(db=db, auth=auth)

        assert result.status_code == 303
        assert "success=Created" in result.headers["location"]
        db.commit.assert_awaited_once()
        # stage should have been called for each new scope
        assert service.stage.await_count > 0

    async def test_all_scopes_already_exist(self, db):
        from auth.api.routes.admin.scopes_pages import seed_default_scopes_submit

        service = MagicMock()
        service.name_exists = AsyncMock(return_value=True)
        service.stage = AsyncMock()

        auth = _make_auth()

        with patch(f"{SCOPES_PAGES_MODULE}._scope_service", service):
            result = await seed_default_scopes_submit(db=db, auth=auth)

        assert result.status_code == 303
        assert "success=All+default+scopes+already+exist" in result.headers["location"]


# ===========================================================================
# PATS PAGES TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# pat_to_dict
# ---------------------------------------------------------------------------


class TestPatToDict:
    def test_basic_conversion(self):
        from auth.api.routes.admin.pats_pages import pat_to_dict

        pat = make_personal_access_token(name="My Token")
        pat.is_expired = False
        result = pat_to_dict(pat, "user@example.com")

        assert result["id"] == str(pat.id)
        assert result["user_id"] == str(pat.user_id)
        assert result["user_email"] == "user@example.com"
        assert result["name"] == "My Token"
        assert result["scopes"] == ["openid"]
        assert result["token_suffix"] == "abcd"
        assert result["is_expired"] is False
        assert result["is_revoked"] is False
        assert result["use_count"] == 0

    def test_revoked_pat(self):
        from auth.api.routes.admin.pats_pages import pat_to_dict

        revoked_time = datetime.now(UTC)
        pat = make_personal_access_token(revoked_at=revoked_time)
        pat.is_expired = False
        result = pat_to_dict(pat)

        assert result["is_revoked"] is True
        assert result["revoked_at"] is not None

    def test_with_tenant_and_client(self):
        from auth.api.routes.admin.pats_pages import pat_to_dict

        pat = make_personal_access_token()
        pat.is_expired = False
        tid = uuid.uuid4()
        cid = uuid.uuid4()
        pat.tenant_id = tid
        pat.target_client_id = cid

        result = pat_to_dict(pat)

        assert result["tenant_id"] == str(tid)
        assert result["target_client_id"] == str(cid)

    def test_none_tenant_and_client(self):
        from auth.api.routes.admin.pats_pages import pat_to_dict

        pat = make_personal_access_token()
        pat.is_expired = False
        result = pat_to_dict(pat)

        assert result["tenant_id"] is None
        assert result["target_client_id"] is None

    def test_no_user_email(self):
        from auth.api.routes.admin.pats_pages import pat_to_dict

        pat = make_personal_access_token()
        pat.is_expired = False
        result = pat_to_dict(pat)

        assert result["user_email"] is None

    def test_timestamps_none(self):
        from auth.api.routes.admin.pats_pages import pat_to_dict

        pat = make_personal_access_token()
        pat.is_expired = False
        pat.created_at = None
        pat.expires_at = None
        pat.last_used_at = None
        pat.revoked_at = None

        result = pat_to_dict(pat)

        assert result["created_at"] is None
        assert result["expires_at"] is None
        assert result["last_used_at"] is None
        assert result["revoked_at"] is None

    def test_last_used_fields(self):
        from auth.api.routes.admin.pats_pages import pat_to_dict

        now = datetime.now(UTC)
        pat = make_personal_access_token(use_count=42)
        pat.is_expired = False
        pat.last_used_at = now
        pat.last_used_ip = "10.0.0.1"

        result = pat_to_dict(pat)

        assert result["last_used_at"] == now.isoformat()
        assert result["last_used_ip"] == "10.0.0.1"
        assert result["use_count"] == 42


# ---------------------------------------------------------------------------
# pats_list_page
# ---------------------------------------------------------------------------


class TestPatsListPage:
    async def test_renders_empty_list(self, db):
        from auth.api.routes.admin.pats_pages import pats_list_page

        request = _make_request()
        auth = _make_auth()
        pat_service = AsyncMock()
        pat_service.list_all_tokens = AsyncMock(return_value=([], 0))

        mock_templates = _mock_templates()

        with (
            patch(f"{PATS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{PATS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await pats_list_page(
                request=request,
                db=db,
                auth=auth,
                pat_service=pat_service,
                page=1,
                include_revoked=False,
                user_id=None,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "pats"
        assert ctx["pats"] == []
        assert ctx["total"] == 0

    async def test_renders_with_pats(self, db):
        from auth.api.routes.admin.pats_pages import pats_list_page

        pat1 = make_personal_access_token(name="Token A")
        pat1.is_expired = False

        # Owner with primary email so _user_service.get_by_id returns a usable model
        email_obj = MagicMock()
        email_obj.email = "a@b.com"
        email_obj.is_primary = True
        mock_owner = MagicMock()
        mock_owner.emails = [email_obj]

        request = _make_request()
        auth = _make_auth()
        pat_service = AsyncMock()
        pat_service.list_all_tokens = AsyncMock(return_value=([pat1], 1))

        mock_templates = _mock_templates()

        with (
            patch(
                f"{PATS_PAGES_MODULE}._user_service.get_by_id",
                new_callable=AsyncMock,
                return_value=mock_owner,
            ),
            patch(f"{PATS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{PATS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await pats_list_page(
                request=request,
                db=db,
                auth=auth,
                pat_service=pat_service,
                page=1,
                include_revoked=False,
                user_id=None,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert len(ctx["pats"]) == 1
        assert ctx["pats"][0]["user_email"] == "a@b.com"

    async def test_invalid_user_id_filter(self, db):
        from auth.api.routes.admin.pats_pages import pats_list_page

        request = _make_request()
        auth = _make_auth()
        pat_service = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await pats_list_page(
                request=request,
                db=db,
                auth=auth,
                pat_service=pat_service,
                page=1,
                include_revoked=False,
                user_id="not-a-uuid",
            )

        assert exc.value.status_code == 400

    async def test_pagination(self, db):
        from auth.api.routes.admin.pats_pages import pats_list_page

        request = _make_request()
        auth = _make_auth()
        pat_service = AsyncMock()
        pat_service.list_all_tokens = AsyncMock(return_value=([], 45))

        mock_templates = _mock_templates()

        with (
            patch(f"{PATS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{PATS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await pats_list_page(
                request=request,
                db=db,
                auth=auth,
                pat_service=pat_service,
                page=2,
                include_revoked=False,
                user_id=None,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["total"] == 45
        assert ctx["total_pages"] == 3  # ceil(45/20)
        assert ctx["page"] == 2

    async def test_reads_query_params(self, db):
        from auth.api.routes.admin.pats_pages import pats_list_page

        request = _make_request({"success": "revoked", "error": "fail"})
        auth = _make_auth()
        pat_service = AsyncMock()
        pat_service.list_all_tokens = AsyncMock(return_value=([], 0))

        mock_templates = _mock_templates()

        with (
            patch(f"{PATS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{PATS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await pats_list_page(
                request=request,
                db=db,
                auth=auth,
                pat_service=pat_service,
                page=1,
                include_revoked=False,
                user_id=None,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["success"] == "revoked"
        assert ctx["error"] == "fail"


# ---------------------------------------------------------------------------
# pat_detail_page
# ---------------------------------------------------------------------------


class TestPatDetailPage:
    async def test_valid_token(self, db):
        from auth.api.routes.admin.pats_pages import pat_detail_page

        pat = make_personal_access_token(name="Detail Token")
        pat.is_expired = False
        token_id = str(pat.id)

        pat_service = AsyncMock()
        pat_service.get_token_by_id = AsyncMock(return_value=pat)

        email_obj = MagicMock()
        email_obj.email = "owner@test.com"
        email_obj.is_primary = True
        mock_owner = MagicMock()
        mock_owner.emails = [email_obj]

        request = _make_request()
        auth = _make_auth()
        mock_templates = _mock_templates()

        with (
            patch(
                f"{PATS_PAGES_MODULE}._user_service.get_by_id",
                new_callable=AsyncMock,
                return_value=mock_owner,
            ),
            patch(f"{PATS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{PATS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await pat_detail_page(
                request=request,
                token_id=token_id,
                db=db,
                auth=auth,
                pat_service=pat_service,
            )

        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert ctx["active_section"] == "pats"
        assert ctx["pat"]["name"] == "Detail Token"
        assert ctx["pat"]["user_email"] == "owner@test.com"

    async def test_invalid_token_id(self, db):
        from auth.api.routes.admin.pats_pages import pat_detail_page

        request = _make_request()
        auth = _make_auth()
        pat_service = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await pat_detail_page(
                request=request,
                token_id="bad-id",
                db=db,
                auth=auth,
                pat_service=pat_service,
            )

        assert exc.value.status_code == 400

    async def test_token_not_found(self, db):
        from auth.api.routes.admin.pats_pages import pat_detail_page

        pat_service = AsyncMock()
        pat_service.get_token_by_id = AsyncMock(return_value=None)

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc:
            await pat_detail_page(
                request=request,
                token_id=str(uuid.uuid4()),
                db=db,
                auth=auth,
                pat_service=pat_service,
            )

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# pat_revoke_submit
# ---------------------------------------------------------------------------


class TestPatRevokeSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.pats_pages import pat_revoke_submit

        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=True)

        token_id = str(uuid.uuid4())
        auth = _make_auth()

        result = await pat_revoke_submit(
            token_id=token_id,
            db=db,
            auth=auth,
            pat_service=pat_service,
            reason="compromised",
        )

        assert result.status_code == 303
        assert "success=Token+revoked" in result.headers["location"]
        db.commit.assert_awaited_once()

    async def test_invalid_token_id(self, db):
        from auth.api.routes.admin.pats_pages import pat_revoke_submit

        pat_service = AsyncMock()
        auth = _make_auth()

        result = await pat_revoke_submit(
            token_id="bad-id",
            db=db,
            auth=auth,
            pat_service=pat_service,
            reason=None,
        )

        assert result.status_code == 303
        assert "error=Invalid+token+ID" in result.headers["location"]

    async def test_token_not_found(self, db):
        from auth.api.routes.admin.pats_pages import pat_revoke_submit

        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=False)

        token_id = str(uuid.uuid4())
        auth = _make_auth()

        result = await pat_revoke_submit(
            token_id=token_id,
            db=db,
            auth=auth,
            pat_service=pat_service,
            reason=None,
        )

        assert result.status_code == 303
        assert "error=Token+not+found" in result.headers["location"]

    async def test_default_reason(self, db):
        from auth.api.routes.admin.pats_pages import pat_revoke_submit

        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=True)

        token_id = str(uuid.uuid4())
        auth = _make_auth()

        await pat_revoke_submit(
            token_id=token_id,
            db=db,
            auth=auth,
            pat_service=pat_service,
            reason=None,
        )

        call_kwargs = pat_service.revoke_token.call_args.kwargs
        assert call_kwargs["reason"] == "Revoked by administrator"

    async def test_custom_reason(self, db):
        from auth.api.routes.admin.pats_pages import pat_revoke_submit

        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=True)

        token_id = str(uuid.uuid4())
        auth = _make_auth()

        await pat_revoke_submit(
            token_id=token_id,
            db=db,
            auth=auth,
            pat_service=pat_service,
            reason="policy violation",
        )

        call_kwargs = pat_service.revoke_token.call_args.kwargs
        assert call_kwargs["reason"] == "policy violation"

    async def test_passes_admin_user_id(self, db):
        from auth.api.routes.admin.pats_pages import pat_revoke_submit

        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=True)

        token_id = str(uuid.uuid4())
        user = make_user()
        auth = (user, [MagicMock()])

        await pat_revoke_submit(
            token_id=token_id,
            db=db,
            auth=auth,
            pat_service=pat_service,
            reason=None,
        )

        call_kwargs = pat_service.revoke_token.call_args.kwargs
        assert call_kwargs["revoked_by"] == user.id


# ---------------------------------------------------------------------------
# pats_revoke_all_submit
# ---------------------------------------------------------------------------


class TestPatsRevokeAllSubmit:
    async def test_success(self, db):
        from auth.api.routes.admin.pats_pages import pats_revoke_all_submit

        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=3)

        user_id = str(uuid.uuid4())
        auth = _make_auth()

        result = await pats_revoke_all_submit(
            db=db,
            auth=auth,
            pat_service=pat_service,
            user_id=user_id,
            reason="cleanup",
        )

        assert result.status_code == 303
        assert "success=Revoked+3" in result.headers["location"]
        db.commit.assert_awaited_once()

    async def test_invalid_user_id(self, db):
        from auth.api.routes.admin.pats_pages import pats_revoke_all_submit

        pat_service = AsyncMock()
        auth = _make_auth()

        result = await pats_revoke_all_submit(
            db=db,
            auth=auth,
            pat_service=pat_service,
            user_id="invalid",
            reason=None,
        )

        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers["location"]

    async def test_default_reason(self, db):
        from auth.api.routes.admin.pats_pages import pats_revoke_all_submit

        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=0)

        auth = _make_auth()
        user_id = str(uuid.uuid4())

        await pats_revoke_all_submit(
            db=db,
            auth=auth,
            pat_service=pat_service,
            user_id=user_id,
            reason=None,
        )

        call_kwargs = pat_service.bulk_revoke.call_args.kwargs
        assert call_kwargs["reason"] == "Bulk revoked by administrator"

    async def test_custom_reason(self, db):
        from auth.api.routes.admin.pats_pages import pats_revoke_all_submit

        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=1)

        auth = _make_auth()
        user_id = str(uuid.uuid4())

        await pats_revoke_all_submit(
            db=db,
            auth=auth,
            pat_service=pat_service,
            user_id=user_id,
            reason="security audit",
        )

        call_kwargs = pat_service.bulk_revoke.call_args.kwargs
        assert call_kwargs["reason"] == "security audit"

    async def test_passes_admin_user_id(self, db):
        from auth.api.routes.admin.pats_pages import pats_revoke_all_submit

        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=2)

        user = make_user()
        auth = (user, [MagicMock()])
        user_id = str(uuid.uuid4())

        await pats_revoke_all_submit(
            db=db,
            auth=auth,
            pat_service=pat_service,
            user_id=user_id,
            reason=None,
        )

        call_kwargs = pat_service.bulk_revoke.call_args.kwargs
        assert call_kwargs["revoked_by"] == user.id

    async def test_zero_revoked(self, db):
        from auth.api.routes.admin.pats_pages import pats_revoke_all_submit

        pat_service = AsyncMock()
        pat_service.bulk_revoke = AsyncMock(return_value=0)

        auth = _make_auth()
        user_id = str(uuid.uuid4())

        result = await pats_revoke_all_submit(
            db=db,
            auth=auth,
            pat_service=pat_service,
            user_id=user_id,
            reason=None,
        )

        assert result.status_code == 303
        assert "success=Revoked+0" in result.headers["location"]


# ---------------------------------------------------------------------------
# Remaining branches
# ---------------------------------------------------------------------------


class TestPatsPrimaryEmail:
    def test_none_user(self):
        from auth.api.routes.admin.pats_pages import _primary_email

        assert _primary_email(None) is None

    def test_no_primary_email(self):
        from auth.api.routes.admin.pats_pages import _primary_email

        user = MagicMock()
        secondary = MagicMock()
        secondary.is_primary = False
        user.emails = [secondary]

        assert _primary_email(user) is None


class TestPatsListPageEmailCache:
    async def test_owner_email_is_resolved_once_per_user(self, db):
        from auth.api.routes.admin.pats_pages import pats_list_page

        owner_id = uuid.uuid4()
        pat1 = make_personal_access_token(name="Token A")
        pat1.user_id = owner_id
        pat1.is_expired = False
        pat2 = make_personal_access_token(name="Token B")
        pat2.user_id = owner_id
        pat2.is_expired = False

        email_obj = MagicMock()
        email_obj.email = "owner@example.com"
        email_obj.is_primary = True
        owner = MagicMock()
        owner.emails = [email_obj]

        pat_service = AsyncMock()
        pat_service.list_all_tokens = AsyncMock(return_value=([pat1, pat2], 2))

        mock_templates = _mock_templates()

        with (
            patch(f"{PATS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{PATS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
            patch(
                f"{PATS_PAGES_MODULE}._user_service.get_by_id",
                AsyncMock(return_value=owner),
            ) as get_by_id,
        ):
            await pats_list_page(
                request=_make_request(),
                db=db,
                auth=_make_auth(),
                pat_service=pat_service,
                page=1,
                include_revoked=False,
                user_id=None,
            )

        get_by_id.assert_awaited_once()
        ctx = mock_templates.TemplateResponse.call_args.kwargs.get("context")
        assert [p["user_email"] for p in ctx["pats"]] == [
            "owner@example.com",
            "owner@example.com",
        ]


class TestScopesListPageActiveFilter:
    @pytest.mark.parametrize(
        ("query_value", "expected"), [("true", True), ("false", False), ("anything", None)]
    )
    async def test_tri_state_is_resolved(self, db, query_value, expected):
        from auth.api.routes.admin.scopes_pages import scopes_list_page

        service = MagicMock()
        service.list = AsyncMock(return_value=([], 0))
        service.count_roles_for_scope = AsyncMock(return_value=0)
        service.list_distinct_categories = AsyncMock(return_value=[])

        with (
            patch(f"{SCOPES_PAGES_MODULE}._scope_service", service),
            patch(f"{SCOPES_PAGES_MODULE}.get_templates", return_value=_mock_templates()),
            patch(
                f"{SCOPES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await scopes_list_page(
                request=_make_request(),
                db=db,
                auth=_make_auth(),
                page=1,
                search=None,
                category=None,
                is_active=query_value,
            )

        assert service.list.await_args.kwargs["is_active"] is expected


class TestSessionsPrimaryEmailFromUser:
    def test_none_user(self):
        from auth.api.routes.admin.sessions_pages import _primary_email_from_user

        assert _primary_email_from_user(None) is None

    def test_user_without_emails(self):
        from auth.api.routes.admin.sessions_pages import _primary_email_from_user

        user = MagicMock()
        user.emails = []

        assert _primary_email_from_user(user) is None

    def test_falls_back_to_first_email(self):
        from auth.api.routes.admin.sessions_pages import _primary_email_from_user

        user = MagicMock()
        first = MagicMock()
        first.is_primary = False
        first.email = "first@example.com"
        user.emails = [first]

        assert _primary_email_from_user(user) == "first@example.com"
