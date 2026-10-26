# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.settings — User account settings endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from tests.conftest import make_execute_result, make_session, make_user

MODULE = "auth.api.routes.auth.settings"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_request(cookies=None, headers=None, query_params=None, base_url="http://localhost/"):
    """Build a mock FastAPI Request."""
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = headers or {}
    request.query_params = query_params or {}
    url = MagicMock()
    url.scheme = "http"
    url.netloc = "localhost"
    url.path = "/auth/settings/profile"
    url.query = ""
    request.url = url
    request.base_url = base_url
    return request


def _mock_templates():
    """Return a mock Jinja2Templates that captures TemplateResponse calls."""
    templates = MagicMock()
    response = MagicMock()
    templates.TemplateResponse.return_value = response
    return templates


def _mock_role(name="user", scopes=None, is_system=False, description=""):
    """Build a mock Role with scope introspection."""
    role = MagicMock()
    role.name = name
    role.description = description
    role.is_system = is_system
    scope_names = scopes or []
    role.get_all_scope_names.return_value = scope_names
    role.role_scopes = []
    return role


def _mock_email(
    email_id=None, email="test@example.com", is_primary=True, is_verified=True, verified_at=None
):
    """Build a mock UserEmail."""
    e = MagicMock()
    e.id = email_id or uuid.uuid4()
    e.email = email
    e.is_primary = is_primary
    e.is_verified = is_verified
    e.verified_at = verified_at or (datetime.now(UTC) if is_verified else None)
    return e


def _mock_profile(**kwargs):
    p = MagicMock()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def _mock_tenant_context(tenant_id=None, tenant_slug=None, resolution_method=None):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.tenant_slug = tenant_slug
    ctx.resolution_method = resolution_method
    return ctx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def session_service():
    return AsyncMock()


@pytest.fixture
def profile_service():
    return AsyncMock()


@pytest.fixture
def password_service():
    return AsyncMock()


@pytest.fixture
def mfa_service():
    return AsyncMock()


@pytest.fixture
def email_service():
    return AsyncMock()


@pytest.fixture
def token_service():
    return AsyncMock()


# ---------------------------------------------------------------------------
# 1. Helpers
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    """Tests for get_tenant_prefix()."""

    def test_no_context(self):
        from auth.api.routes.auth.settings import get_tenant_prefix

        with patch(f"{MODULE}.get_tenant_context", return_value=None):
            assert get_tenant_prefix() == ""

    def test_context_with_path_resolution(self):
        from auth.api.routes.auth.settings import get_tenant_prefix

        ctx = _mock_tenant_context(tenant_slug="acme", resolution_method="path")
        with patch(f"{MODULE}.get_tenant_context", return_value=ctx):
            assert get_tenant_prefix() == "/t/acme"

    def test_context_with_subdomain_resolution(self):
        from auth.api.routes.auth.settings import get_tenant_prefix

        ctx = _mock_tenant_context(tenant_slug="acme", resolution_method="subdomain")
        with patch(f"{MODULE}.get_tenant_context", return_value=ctx):
            assert get_tenant_prefix() == ""

    def test_context_with_no_slug(self):
        from auth.api.routes.auth.settings import get_tenant_prefix

        ctx = _mock_tenant_context(tenant_slug=None, resolution_method="path")
        with patch(f"{MODULE}.get_tenant_context", return_value=ctx):
            assert get_tenant_prefix() == ""


class TestSettingsRedirect:
    """Tests for settings_redirect()."""

    def test_basic_redirect(self):
        from auth.api.routes.auth.settings import settings_redirect

        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            resp = settings_redirect("/emails")
        assert resp.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/settings/emails" in resp.headers["location"]

    def test_redirect_with_query_params(self):
        from auth.api.routes.auth.settings import settings_redirect

        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            resp = settings_redirect("/emails", error="bad stuff")
        loc = resp.headers["location"]
        assert "error=bad" in loc

    def test_redirect_with_tenant_prefix(self):
        from auth.api.routes.auth.settings import settings_redirect

        with patch(f"{MODULE}.get_tenant_prefix", return_value="/t/acme"):
            resp = settings_redirect("/profile")
        assert resp.headers["location"].startswith("/t/acme/auth/settings/profile")


class TestGetBrandingForRequest:
    """Tests for get_branding_for_request()."""

    async def test_no_tenant_returns_default(self, db):
        from auth.api.routes.auth.settings import get_branding_for_request

        with patch(f"{MODULE}.get_tenant_context", return_value=None):
            result = await get_branding_for_request(db)
        from auth.services.branding import BrandingConfig

        assert isinstance(result, BrandingConfig)

    async def test_with_tenant_calls_branding_service(self, db):
        from auth.api.routes.auth.settings import get_branding_for_request

        ctx = _mock_tenant_context(tenant_id="tid")
        branding_mock = MagicMock()
        with (
            patch(f"{MODULE}.get_tenant_context", return_value=ctx),
            patch(f"{MODULE}.BrandingService") as MockBS,
        ):
            instance = MockBS.return_value
            instance.get_branding = AsyncMock(return_value=branding_mock)
            result = await get_branding_for_request(db)
        assert result is branding_mock


class TestGetCurrentUserLocal:
    """Tests for the local get_current_user() in settings.py."""

    async def test_no_session_token_raises(self, db, session_service):
        from auth.api.routes.auth.settings import get_current_user

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(request, db, session_service)
        assert exc_info.value.status_code == 401

    async def test_invalid_session_raises(self, db, session_service):
        from auth.api.routes.auth.settings import get_current_user

        request = _mock_request(cookies={"session": "bad-token"})
        session_service.get_user_by_session_token = AsyncMock(return_value=None)
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(request, db, session_service)
        assert exc_info.value.status_code == 401

    async def test_valid_session_returns_user(self, db, session_service):
        from auth.api.routes.auth.settings import get_current_user

        user = make_user()
        request = _mock_request(cookies={"session": "good-token"})
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await get_current_user(request, db, session_service)
        assert result is user


class TestBuildCurrentUrl:
    """Tests for _build_current_url()."""

    def test_basic_url(self):
        from auth.api.routes.auth.settings import _build_current_url

        request = _mock_request()
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            url = _build_current_url(request)
        assert "://localhost" in url
        assert "/auth/settings/profile" in url

    def test_with_proxy_headers(self):
        from auth.api.routes.auth.settings import _build_current_url

        request = _mock_request(
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "auth.example.com",
            }
        )
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            url = _build_current_url(request)
        assert url.startswith("https://auth.example.com")

    def test_with_query_string(self):
        from auth.api.routes.auth.settings import _build_current_url

        request = _mock_request()
        request.url.query = "foo=bar"
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            url = _build_current_url(request)
        assert "?foo=bar" in url


class TestRequireAuthRedirect:
    """Tests for require_auth_redirect()."""

    def test_redirect_to_login(self):
        from auth.api.routes.auth.settings import require_auth_redirect

        request = _mock_request()
        with (
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(
                f"{MODULE}._build_current_url",
                return_value="http://localhost/auth/settings/profile",
            ),
        ):
            resp = require_auth_redirect(request)
        assert resp.status_code == status.HTTP_302_FOUND
        assert "/auth/login" in resp.headers["location"]
        assert "next=" in resp.headers["location"]


class TestCheckUserIsAdmin:
    """Tests for check_user_is_admin()."""

    async def test_admin_user(self, db):
        from auth.api.routes.auth.settings import check_user_is_admin

        user = make_user()
        role = _mock_role(name="admin", scopes=["users:read"])
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[role]))

        with patch(
            f"{MODULE}.get_user_admin_permissions",
            return_value={"can_view_users": True, "can_view_clients": False},
        ):
            is_admin, perms = await check_user_is_admin(db, user)
        assert is_admin is True
        assert perms["can_view_users"] is True

    async def test_non_admin_user(self, db):
        from auth.api.routes.auth.settings import check_user_is_admin

        user = make_user()
        role = _mock_role(name="basic", scopes=[])
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[role]))

        with patch(
            f"{MODULE}.get_user_admin_permissions",
            return_value={"can_view_users": False, "can_view_clients": False},
        ):
            is_admin, perms = await check_user_is_admin(db, user)
        assert is_admin is False


# ---------------------------------------------------------------------------
# 2. Profile Endpoints
# ---------------------------------------------------------------------------


class TestSettingsIndex:
    """Tests for settings_index()."""

    async def test_redirects_to_profile(self):
        from auth.api.routes.auth.settings import settings_index

        request = _mock_request()
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            resp = await settings_index(request)
        assert resp.status_code == status.HTTP_302_FOUND
        assert "/auth/settings/profile" in resp.headers["location"]

    async def test_redirects_with_tenant_prefix(self):
        from auth.api.routes.auth.settings import settings_index

        request = _mock_request()
        with patch(f"{MODULE}.get_tenant_prefix", return_value="/t/acme"):
            resp = await settings_index(request)
        assert "/t/acme/auth/settings/profile" in resp.headers["location"]


class TestSettingsProfile:
    """Tests for settings_profile() GET."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_profile

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_profile(request, db, session_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_invalid_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_profile

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "bad"})
        session_service.get_user_by_session_token = AsyncMock(return_value=None)
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_profile(request, db, session_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_valid_session_renders_profile(self, db, session_service):
        from auth.api.routes.auth.settings import settings_profile

        user = make_user()
        primary_email = _mock_email(is_primary=True)
        user.profile = _mock_profile(nickname="nick")
        user.emails = [primary_email]

        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        role = _mock_role(name="user", scopes=[])
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[role]))

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>profile</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_profile(request, db, session_service, branding_service)
        branding_service.render_template.assert_awaited_once()
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["active_section"] == "profile"
        assert ctx["user"] is user


class TestSettingsProfileUpdate:
    """Tests for settings_profile_update() POST."""

    async def test_no_session_redirects(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import settings_profile_update

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_profile_update(
                request,
                db,
                session_service,
                profile_service,
                branding_service,
            )
        mock_redirect.assert_called_once()

    async def test_valid_update(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import settings_profile_update

        user = make_user()
        user.emails = [_mock_email(is_primary=True)]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        updated_profile = _mock_profile(nickname="new-nick")
        profile_service.update_profile = AsyncMock(return_value=updated_profile)

        role = _mock_role(name="user", scopes=[])
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[role]))

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>updated</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_profile_update(
                request,
                db,
                session_service,
                profile_service,
                branding_service,
                nickname="new-nick",
            )
        branding_service.render_template.assert_awaited_once()
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["success"] == "Profile updated successfully."
        db.commit.assert_awaited_once()


class TestSettingsUploadAvatar:
    """Tests for settings_upload_avatar() POST."""

    async def test_no_session_redirects(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import settings_upload_avatar

        request = _mock_request(cookies={})
        avatar = MagicMock()
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_templates", return_value=_mock_templates()),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_upload_avatar(request, db, session_service, profile_service, avatar)
        mock_redirect.assert_called_once()

    async def test_successful_upload(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import settings_upload_avatar

        user = make_user()
        user.emails = [_mock_email()]
        user.profile = _mock_profile()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        profile_service.update_profile = AsyncMock(return_value=_mock_profile())

        templates = _mock_templates()
        request = _mock_request(cookies={"session": "good"})
        avatar = MagicMock()

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_templates", return_value=templates),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(
                f"{MODULE}.get_branding_for_request",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.upload_service") as mock_upload,
        ):
            mock_upload.save_avatar = AsyncMock(return_value="avatars/abc.jpg")
            mock_upload.get_avatar_url.return_value = "/uploads/avatars/abc.jpg"
            await settings_upload_avatar(request, db, session_service, profile_service, avatar)
        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["success"] is not None
        assert ctx["error"] is None

    async def test_upload_error(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import UploadError, settings_upload_avatar

        user = make_user()
        user.emails = [_mock_email()]
        user.profile = _mock_profile()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        templates = _mock_templates()
        request = _mock_request(cookies={"session": "good"})
        avatar = MagicMock()

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_templates", return_value=templates),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(
                f"{MODULE}.get_branding_for_request",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.upload_service") as mock_upload,
        ):
            mock_upload.save_avatar = AsyncMock(side_effect=UploadError("File too large"))
            await settings_upload_avatar(request, db, session_service, profile_service, avatar)
        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["error"] == "File too large"
        assert ctx["success"] is None


class TestUploadAvatarApi:
    """Tests for upload_avatar_api() POST."""

    async def test_unauthenticated(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import upload_avatar_api

        request = _mock_request(cookies={})
        avatar = MagicMock()
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await upload_avatar_api(request, db, session_service, profile_service, avatar)
        assert resp.status_code == 401

    async def test_success(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import upload_avatar_api

        user = make_user()
        request = _mock_request(cookies={"session": "good"})
        avatar = MagicMock()

        with (
            patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user),
            patch(f"{MODULE}.upload_service") as mock_upload,
        ):
            mock_upload.save_avatar = AsyncMock(return_value="avatars/abc.jpg")
            mock_upload.get_avatar_url.return_value = "/uploads/avatars/abc.jpg"
            profile_service.update_profile = AsyncMock(return_value=_mock_profile())
            resp = await upload_avatar_api(request, db, session_service, profile_service, avatar)
        assert resp.status_code == 200
        assert resp.body is not None

    async def test_upload_error(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import UploadError, upload_avatar_api

        user = make_user()
        request = _mock_request(cookies={"session": "good"})
        avatar = MagicMock()

        with (
            patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user),
            patch(f"{MODULE}.upload_service") as mock_upload,
        ):
            mock_upload.save_avatar = AsyncMock(side_effect=UploadError("Invalid format"))
            resp = await upload_avatar_api(request, db, session_service, profile_service, avatar)
        assert resp.status_code == 400


class TestGetProfileApi:
    """Tests for get_profile_api() GET."""

    async def test_unauthenticated(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import get_profile_api

        request = _mock_request(cookies={})
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await get_profile_api(request, db, session_service, profile_service)
        assert resp.status_code == 401

    async def test_success(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import get_profile_api

        user = make_user()
        profile = _mock_profile(nickname="nick")
        profile_service.get_profile = AsyncMock(return_value=profile)
        profile_service.profile_to_dict = MagicMock(return_value={"nickname": "nick"})
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await get_profile_api(request, db, session_service, profile_service)
        assert resp.status_code == 200


class TestUpdateProfileApi:
    """Tests for update_profile_api() PUT."""

    async def test_unauthenticated(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import ProfileUpdateRequest, update_profile_api

        request = _mock_request(cookies={})
        data = ProfileUpdateRequest(nickname="test")
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await update_profile_api(request, db, session_service, profile_service, data)
        assert resp.status_code == 401

    async def test_success(self, db, session_service, profile_service):
        from auth.api.routes.auth.settings import ProfileUpdateRequest, update_profile_api

        user = make_user()
        profile = _mock_profile(nickname="updated")
        profile_service.update_profile = AsyncMock(return_value=profile)
        profile_service.profile_to_dict = MagicMock(return_value={"nickname": "updated"})
        data = ProfileUpdateRequest(nickname="updated")
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await update_profile_api(request, db, session_service, profile_service, data)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. Password Endpoints
# ---------------------------------------------------------------------------


class TestSettingsPassword:
    """Tests for settings_password() GET."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_password

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_password(request, db, session_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_valid_session_renders(self, db, session_service):
        from auth.api.routes.auth.settings import settings_password

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>password</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_password(request, db, session_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["active_section"] == "password"


class TestSettingsPasswordUpdate:
    """Tests for settings_password_update() POST."""

    async def test_no_session_redirects(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import settings_password_update

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_password_update(
                request,
                db,
                session_service,
                password_service,
                branding_service,
                current_password="old",
                new_password="newpassword",
                confirm_password="newpassword",
            )
        mock_redirect.assert_called_once()

    async def test_passwords_dont_match(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import settings_password_update

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_password_update(
                request,
                db,
                session_service,
                password_service,
                branding_service,
                current_password="old",
                new_password="newpass12",
                confirm_password="mismatch",
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["error"] == "New passwords do not match."

    async def test_password_too_short(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import settings_password_update

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_password_update(
                request,
                db,
                session_service,
                password_service,
                branding_service,
                current_password="old",
                new_password="short",
                confirm_password="short",
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["error"] == "Password must be at least 8 characters."

    async def test_change_password_failure(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import settings_password_update

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        password_service.change_password = AsyncMock(
            return_value=(False, "Current password incorrect")
        )
        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_password_update(
                request,
                db,
                session_service,
                password_service,
                branding_service,
                current_password="wrong",
                new_password="newpassword",
                confirm_password="newpassword",
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["error"] == "Current password incorrect"

    async def test_successful_password_change(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import settings_password_update

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        password_service.change_password = AsyncMock(return_value=(True, None))
        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_password_update(
                request,
                db,
                session_service,
                password_service,
                branding_service,
                current_password="old",
                new_password="newpassword",
                confirm_password="newpassword",
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["success"] == "Password changed successfully."
        assert ctx["error"] is None


class TestUpdatePasswordApi:
    """Tests for update_password_api() PUT."""

    async def test_unauthenticated(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import PasswordChangeRequest, update_password_api

        request = _mock_request(cookies={})
        data = PasswordChangeRequest(current_password="old", new_password="newpassword")
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await update_password_api(request, db, session_service, password_service, data)
        assert resp.status_code == 401

    async def test_password_too_short(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import PasswordChangeRequest, update_password_api

        user = make_user()
        data = PasswordChangeRequest(current_password="old", new_password="short")
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await update_password_api(request, db, session_service, password_service, data)
        assert resp.status_code == 400

    async def test_change_failure(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import PasswordChangeRequest, update_password_api

        user = make_user()
        password_service.change_password = AsyncMock(return_value=(False, "Wrong password"))
        data = PasswordChangeRequest(current_password="wrong", new_password="newpassword")
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await update_password_api(request, db, session_service, password_service, data)
        assert resp.status_code == 400

    async def test_success(self, db, session_service, password_service):
        from auth.api.routes.auth.settings import PasswordChangeRequest, update_password_api

        user = make_user()
        password_service.change_password = AsyncMock(return_value=(True, None))
        data = PasswordChangeRequest(current_password="old", new_password="newpassword")
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await update_password_api(request, db, session_service, password_service, data)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. Security
# ---------------------------------------------------------------------------


class TestSettingsSecurity:
    """Tests for settings_security() GET."""

    async def test_no_session_redirects(self, db, session_service, mfa_service):
        from auth.api.routes.auth.settings import settings_security

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_security(request, db, session_service, mfa_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_totp_enabled(self, db, session_service, mfa_service):
        from auth.api.routes.auth.settings import settings_security

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        mfa_mock = MagicMock()
        mfa_mock.totp_enabled = True
        mfa_service.get_user_mfa = AsyncMock(return_value=mfa_mock)
        mfa_service.get_backup_codes_status = AsyncMock(return_value=(5, 10))

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>security</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_security(request, db, session_service, mfa_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["totp_enabled"] is True
        assert ctx["backup_codes_remaining"] == 5
        assert ctx["backup_codes_total"] == 10

    async def test_totp_disabled(self, db, session_service, mfa_service):
        from auth.api.routes.auth.settings import settings_security

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        mfa_service.get_user_mfa = AsyncMock(return_value=None)

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>security</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_security(request, db, session_service, mfa_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["totp_enabled"] is False
        assert ctx["backup_codes_remaining"] is None


# ---------------------------------------------------------------------------
# 5. Sessions
# ---------------------------------------------------------------------------


class TestSettingsSessions:
    """Tests for settings_sessions() GET."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_sessions

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_sessions(request, db, session_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_valid_session_renders(self, db, session_service):
        from auth.api.routes.auth.settings import settings_sessions

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        session_service.get_user_sessions = AsyncMock(return_value=[current])

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>sessions</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_sessions(request, db, session_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["active_section"] == "sessions"
        assert len(ctx["sessions"]) == 1


class TestSettingsRevokeSession:
    """Tests for settings_revoke_session() POST."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_revoke_session

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_revoke_session(request, "some-id", db, session_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_cannot_revoke_current(self, db, session_service):
        from auth.api.routes.auth.settings import settings_revoke_session

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        session_service.get_user_sessions = AsyncMock(return_value=[current])

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_revoke_session(
                request, str(current.id), db, session_service, branding_service
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["error"] == "Cannot revoke the current session."

    async def test_successful_revoke(self, db, session_service):
        from auth.api.routes.auth.settings import settings_revoke_session

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        session_service.revoke_session_by_id = AsyncMock(return_value=True)
        session_service.get_user_sessions = AsyncMock(return_value=[current])

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})
        other_id = str(uuid.uuid4())

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_revoke_session(request, other_id, db, session_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["success"] == "Session revoked successfully."

    async def test_revoke_not_found(self, db, session_service):
        from auth.api.routes.auth.settings import settings_revoke_session

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        session_service.revoke_session_by_id = AsyncMock(return_value=False)
        session_service.get_user_sessions = AsyncMock(return_value=[current])

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_revoke_session(
                request, str(uuid.uuid4()), db, session_service, branding_service
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["error"] == "Session not found or already revoked."


class TestSettingsRevokeAllSessions:
    """Tests for settings_revoke_all_sessions() POST."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_revoke_all_sessions

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_revoke_all_sessions(request, db, session_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_success(self, db, session_service):
        from auth.api.routes.auth.settings import settings_revoke_all_sessions

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        session_service.revoke_all_user_sessions = AsyncMock(return_value=3)
        session_service.get_user_sessions = AsyncMock(return_value=[current])

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_revoke_all_sessions(request, db, session_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert "3" in ctx["success"]


class TestGetSessionsApi:
    """Tests for get_sessions_api()."""

    async def test_unauthenticated(self, db, session_service):
        from auth.api.routes.auth.settings import get_sessions_api

        request = _mock_request(cookies={})
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await get_sessions_api(request, db, session_service)
        assert resp.status_code == 401

    async def test_success(self, db, session_service):
        from auth.api.routes.auth.settings import get_sessions_api

        user = make_user()
        sess = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=sess)
        session_service.get_user_sessions = AsyncMock(return_value=[sess])
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user),
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
        ):
            resp = await get_sessions_api(request, db, session_service)
        assert resp.status_code == 200


class TestDeleteSessionApi:
    """Tests for delete_session_api()."""

    async def test_unauthenticated(self, db, session_service):
        from auth.api.routes.auth.settings import delete_session_api

        request = _mock_request(cookies={})
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await delete_session_api(request, "some-id", db, session_service)
        assert resp.status_code == 401

    async def test_cannot_revoke_current(self, db, session_service):
        from auth.api.routes.auth.settings import delete_session_api

        user = make_user()
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user),
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
        ):
            resp = await delete_session_api(request, str(current.id), db, session_service)
        assert resp.status_code == 400

    async def test_not_found(self, db, session_service):
        from auth.api.routes.auth.settings import delete_session_api

        user = make_user()
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        session_service.revoke_session_by_id = AsyncMock(return_value=False)
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user),
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
        ):
            resp = await delete_session_api(request, str(uuid.uuid4()), db, session_service)
        assert resp.status_code == 404

    async def test_success(self, db, session_service):
        from auth.api.routes.auth.settings import delete_session_api

        user = make_user()
        current = make_session(user_id=user.id)
        session_service.get_session = AsyncMock(return_value=current)
        session_service.revoke_session_by_id = AsyncMock(return_value=True)
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user),
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
        ):
            resp = await delete_session_api(request, str(uuid.uuid4()), db, session_service)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 6. Applications
# ---------------------------------------------------------------------------


class TestSettingsApplications:
    """Tests for settings_applications() GET."""

    async def test_no_session_redirects(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import settings_applications

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_applications(
                request, db, session_service, token_service, branding_service
            )
        mock_redirect.assert_called_once()

    async def test_renders_with_apps(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import settings_applications

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        apps = [{"client_id": "c1", "name": "App1"}]
        token_service.get_user_authorized_clients = AsyncMock(return_value=apps)

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>apps</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_applications(
                request, db, session_service, token_service, branding_service
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["active_section"] == "applications"
        assert ctx["applications"] == apps


class TestSettingsRevokeApplication:
    """Tests for settings_revoke_application() POST."""

    async def test_no_session_redirects(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import settings_revoke_application

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_revoke_application(
                request, "c1", db, session_service, token_service, branding_service
            )
        mock_redirect.assert_called_once()

    async def test_successful_revoke(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import settings_revoke_application

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        token_service.revoke_client_access = AsyncMock(return_value=2)
        token_service.get_user_authorized_clients = AsyncMock(return_value=[])

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_revoke_application(
                request, "c1", db, session_service, token_service, branding_service
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["success"] is not None

    async def test_revoke_not_found(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import settings_revoke_application

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        token_service.revoke_client_access = AsyncMock(return_value=0)
        token_service.get_user_authorized_clients = AsyncMock(return_value=[])

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_revoke_application(
                request, "c1", db, session_service, token_service, branding_service
            )
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["error"] == "Application not found or already revoked."


class TestGetApplicationsApi:
    """Tests for get_applications_api()."""

    async def test_unauthenticated(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import get_applications_api

        request = _mock_request(cookies={})
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await get_applications_api(request, db, session_service, token_service)
        assert resp.status_code == 401

    async def test_success(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import get_applications_api

        user = make_user()
        now = datetime.now(UTC)
        apps = [
            {
                "client_id": "c1",
                "name": "App1",
                "description": "desc",
                "scopes": ["openid"],
                "authorized_at": now,
                "last_used": now,
            },
        ]
        token_service.get_user_authorized_clients = AsyncMock(return_value=apps)
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await get_applications_api(request, db, session_service, token_service)
        assert resp.status_code == 200


class TestDeleteApplicationApi:
    """Tests for delete_application_api()."""

    async def test_unauthenticated(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import delete_application_api

        request = _mock_request(cookies={})
        with patch(
            f"{MODULE}.get_current_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401),
        ):
            resp = await delete_application_api(request, "c1", db, session_service, token_service)
        assert resp.status_code == 401

    async def test_not_found(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import delete_application_api

        user = make_user()
        token_service.revoke_client_access = AsyncMock(return_value=0)
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await delete_application_api(request, "c1", db, session_service, token_service)
        assert resp.status_code == 404

    async def test_success(self, db, session_service, token_service):
        from auth.api.routes.auth.settings import delete_application_api

        user = make_user()
        token_service.revoke_client_access = AsyncMock(return_value=3)
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_current_user", new_callable=AsyncMock, return_value=user):
            resp = await delete_application_api(request, "c1", db, session_service, token_service)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 7. Email Management
# ---------------------------------------------------------------------------


class TestSettingsEmails:
    """Tests for settings_emails() GET."""

    async def test_no_session_redirects(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_emails

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_emails(request, db, session_service, email_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_renders_emails(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_emails

        user = make_user()
        primary = _mock_email(email="primary@example.com", is_primary=True, is_verified=True)
        secondary = _mock_email(
            email="secondary@example.com", is_primary=False, is_verified=False, verified_at=None
        )
        user.emails = [primary, secondary]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        email_service.has_valid_verification_code = AsyncMock(return_value=False)

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>emails</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_emails(request, db, session_service, email_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["active_section"] == "emails"
        assert len(ctx["emails"]) == 2


class TestSettingsAddEmailRedirect:
    """Tests for settings_add_email_redirect() GET."""

    async def test_redirects_to_emails(self):
        from auth.api.routes.auth.settings import settings_add_email_redirect

        request = _mock_request()
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            resp = await settings_add_email_redirect(request)
        assert resp.status_code == status.HTTP_302_FOUND
        assert "/auth/settings/emails" in resp.headers["location"]


class TestSettingsAddEmail:
    """Tests for settings_add_email() POST."""

    async def test_no_session_redirects(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_add_email

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_add_email(
                request, db, session_service, email_service, email="new@example.com"
            )
        mock_redirect.assert_called_once()

    async def test_email_already_exists(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_add_email

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        existing = _mock_email(email="existing@example.com")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=existing))

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_add_email(
                request, db, session_service, email_service, email="existing@example.com"
            )
        mock_sr.assert_called_with("/emails", error="Email address already registered")

    async def test_success_with_verification_sent(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_add_email

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        email_service.send_verification_email = AsyncMock(return_value=True)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
            patch(f"{MODULE}.get_tenant_context", return_value=None),
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_add_email(
                request, db, session_service, email_service, email="new@example.com"
            )
        mock_sr.assert_called_with(
            "/emails", success="Email added. Please check your inbox to verify it."
        )
        db.commit.assert_awaited_once()

    async def test_verification_email_fails(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_add_email

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        email_service.send_verification_email = AsyncMock(return_value=False)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
            patch(f"{MODULE}.get_tenant_context", return_value=None),
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_add_email(
                request, db, session_service, email_service, email="new@example.com"
            )
        args, kwargs = mock_sr.call_args
        assert "could not be sent" in kwargs.get("success", "")


class TestSettingsRemoveEmail:
    """Tests for settings_remove_email() POST."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_remove_email

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_remove_email(request, "eid", db, session_service)
        mock_redirect.assert_called_once()

    async def test_email_not_found(self, db, session_service):
        from auth.api.routes.auth.settings import settings_remove_email

        user = make_user()
        user.emails = []
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_remove_email(request, str(uuid.uuid4()), db, session_service)
        mock_sr.assert_called_with("/emails", error="Email not found")

    async def test_cannot_remove_primary(self, db, session_service):
        from auth.api.routes.auth.settings import settings_remove_email

        user = make_user()
        email = _mock_email(is_primary=True)
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_remove_email(request, str(email.id), db, session_service)
        mock_sr.assert_called_with(
            "/emails", error="Cannot remove primary email. Set another email as primary first."
        )

    async def test_cannot_remove_last_email(self, db, session_service):
        from auth.api.routes.auth.settings import settings_remove_email

        user = make_user()
        email = _mock_email(is_primary=False)
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_remove_email(request, str(email.id), db, session_service)
        mock_sr.assert_called_with("/emails", error="Cannot remove your only email address")

    async def test_successful_removal(self, db, session_service):
        from auth.api.routes.auth.settings import settings_remove_email

        user = make_user()
        primary = _mock_email(is_primary=True, email="primary@example.com")
        secondary = _mock_email(is_primary=False, email="secondary@example.com")
        user.emails = [primary, secondary]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_remove_email(request, str(secondary.id), db, session_service)
        mock_sr.assert_called_with("/emails", success="Email removed successfully")
        db.delete.assert_awaited_once()
        db.commit.assert_awaited_once()


class TestSettingsSetPrimaryEmail:
    """Tests for settings_set_primary_email() POST."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_set_primary_email

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_set_primary_email(request, "eid", db, session_service)
        mock_redirect.assert_called_once()

    async def test_email_not_found(self, db, session_service):
        from auth.api.routes.auth.settings import settings_set_primary_email

        user = make_user()
        user.emails = []
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_set_primary_email(request, str(uuid.uuid4()), db, session_service)
        mock_sr.assert_called_with("/emails", error="Email not found")

    async def test_unverified_cannot_be_primary(self, db, session_service):
        from auth.api.routes.auth.settings import settings_set_primary_email

        user = make_user()
        email = _mock_email(is_primary=False, is_verified=False)
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_set_primary_email(request, str(email.id), db, session_service)
        mock_sr.assert_called_with(
            "/emails", error="Email must be verified before setting as primary"
        )

    async def test_already_primary(self, db, session_service):
        from auth.api.routes.auth.settings import settings_set_primary_email

        user = make_user()
        email = _mock_email(is_primary=True, is_verified=True)
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_set_primary_email(request, str(email.id), db, session_service)
        mock_sr.assert_called_with("/emails", error="This email is already primary")

    async def test_success(self, db, session_service):
        from auth.api.routes.auth.settings import settings_set_primary_email

        user = make_user()
        old_primary = _mock_email(is_primary=True, is_verified=True, email="old@example.com")
        new_primary = _mock_email(is_primary=False, is_verified=True, email="new@example.com")
        user.emails = [old_primary, new_primary]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_set_primary_email(request, str(new_primary.id), db, session_service)
        mock_sr.assert_called_with("/emails", success="Primary email updated successfully")
        db.commit.assert_awaited_once()


class TestSettingsVerifyEmailRedirect:
    """Tests for settings_verify_email_redirect() GET."""

    async def test_redirects_to_emails(self):
        from auth.api.routes.auth.settings import settings_verify_email_redirect

        request = _mock_request()
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            resp = await settings_verify_email_redirect(request, "eid")
        assert resp.status_code == status.HTTP_302_FOUND
        assert "/auth/settings/emails" in resp.headers["location"]


class TestSettingsVerifyEmail:
    """Tests for settings_verify_email() POST."""

    async def test_no_session_redirects(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_verify_email

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_verify_email(
                request, "eid", "123456", db, session_service, email_service
            )
        mock_redirect.assert_called_once()

    async def test_email_not_found(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_verify_email

        user = make_user()
        user.emails = []
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_verify_email(
                request, str(uuid.uuid4()), "123456", db, session_service, email_service
            )
        mock_sr.assert_called_with("/emails", error="Email not found")

    async def test_already_verified(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_verify_email

        user = make_user()
        email = _mock_email(is_verified=True)
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_verify_email(
                request, str(email.id), "123456", db, session_service, email_service
            )
        mock_sr.assert_called_with("/emails", error="Email is already verified")

    async def test_invalid_code(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_verify_email

        user = make_user()
        email = _mock_email(is_verified=False)
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        email_service.verify_code = AsyncMock(return_value=False)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_verify_email(
                request, str(email.id), "wrong", db, session_service, email_service
            )
        mock_sr.assert_called_with("/emails", error="Invalid or expired verification code")

    async def test_success(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_verify_email

        user = make_user()
        email = _mock_email(is_verified=False, email="test@example.com")
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        email_service.verify_code = AsyncMock(return_value=True)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_verify_email(
                request, str(email.id), "123456", db, session_service, email_service
            )
        mock_sr.assert_called_with("/emails", success="Email verified successfully")


class TestSettingsResendEmailVerification:
    """Tests for settings_resend_email_verification() POST."""

    async def test_no_session_redirects(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_resend_email_verification

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_resend_email_verification(
                request, "eid", db, session_service, email_service
            )
        mock_redirect.assert_called_once()

    async def test_email_not_found(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_resend_email_verification

        user = make_user()
        user.emails = []
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_resend_email_verification(
                request, str(uuid.uuid4()), db, session_service, email_service
            )
        mock_sr.assert_called_with("/emails", error="Email not found")

    async def test_already_verified(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_resend_email_verification

        user = make_user()
        email = _mock_email(is_verified=True)
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_resend_email_verification(
                request, str(email.id), db, session_service, email_service
            )
        mock_sr.assert_called_with("/emails", error="Email is already verified")

    async def test_send_failure(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_resend_email_verification

        user = make_user()
        email = _mock_email(is_verified=False, email="test@example.com")
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        email_service.send_verification_email = AsyncMock(return_value=False)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
            patch(f"{MODULE}.get_tenant_context", return_value=None),
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_resend_email_verification(
                request, str(email.id), db, session_service, email_service
            )
        args, kwargs = mock_sr.call_args
        assert "Failed to send" in kwargs.get("error", "")

    async def test_success(self, db, session_service, email_service):
        from auth.api.routes.auth.settings import settings_resend_email_verification

        user = make_user()
        email = _mock_email(is_verified=False, email="test@example.com")
        user.emails = [email]
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        email_service.send_verification_email = AsyncMock(return_value=True)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
            patch(f"{MODULE}.get_tenant_context", return_value=None),
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_resend_email_verification(
                request, str(email.id), db, session_service, email_service
            )
        mock_sr.assert_called_with(
            "/emails", success="Verification email sent. Please check your inbox."
        )


# ---------------------------------------------------------------------------
# 8. Organisations
# ---------------------------------------------------------------------------


class TestSettingsTenants:
    """Tests for settings_tenants() GET."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_tenants

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_tenants(request, db, session_service, branding_service)
        mock_redirect.assert_called_once()

    async def test_renders_memberships(self, db, session_service):
        from auth.api.routes.auth.settings import settings_tenants

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        # Mock empty memberships and federated identities
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        branding_service = MagicMock()
        branding_service.render_template = AsyncMock(return_value="<html>tenants</html>")
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.check_user_is_admin", new_callable=AsyncMock, return_value=(False, {})
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_tenants(request, db, session_service, branding_service)
        ctx = branding_service.render_template.call_args.args[2]
        assert ctx["active_section"] == "tenants"


class TestSettingsLeaveTenant:
    """Tests for settings_leave_tenant() POST."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_leave_tenant

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_leave_tenant(request, str(uuid.uuid4()), db, session_service)
        mock_redirect.assert_called_once()

    async def test_invalid_tenant_id(self, db, session_service):
        from auth.api.routes.auth.settings import settings_leave_tenant

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_leave_tenant(request, "not-a-uuid", db, session_service)
        mock_sr.assert_called_with("/organisations", error="Invalid tenant ID")

    async def test_not_a_member(self, db, session_service):
        from auth.api.routes.auth.settings import settings_leave_tenant

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        request = _mock_request(cookies={"session": "good"})
        tid = str(uuid.uuid4())
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_leave_tenant(request, tid, db, session_service)
        mock_sr.assert_called_with("/organisations", error="You are not a member of this tenant")

    async def test_only_owner_cannot_leave(self, db, session_service):
        from auth.api.routes.auth.settings import settings_leave_tenant

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        membership = MagicMock()
        membership.has_scope.return_value = True  # user is owner

        # First execute: find membership. Second execute: count owners
        owner_member = MagicMock()
        owner_member.has_scope.return_value = True
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=membership),
                make_execute_result(scalars_list=[owner_member]),
            ]
        )

        request = _mock_request(cookies={"session": "good"})
        tid = str(uuid.uuid4())
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_leave_tenant(request, tid, db, session_service)
        args, kwargs = mock_sr.call_args
        assert "only owner" in kwargs.get(
            "error", ""
        ).lower() or "Transfer ownership" in kwargs.get("error", "")


class TestSettingsUnlinkTenantIdp:
    """Tests for settings_unlink_tenant_idp() POST."""

    async def test_no_session_redirects(self, db, session_service):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.require_auth_redirect") as mock_redirect,
        ):
            mock_redirect.return_value = MagicMock(status_code=302)
            await settings_unlink_tenant_idp(
                request, str(uuid.uuid4()), str(uuid.uuid4()), db, session_service
            )
        mock_redirect.assert_called_once()

    async def test_invalid_idp_id(self, db, session_service):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_unlink_tenant_idp(
                request, str(uuid.uuid4()), "not-a-uuid", db, session_service
            )
        mock_sr.assert_called_with("/organisations", error="Invalid IdP ID")

    async def test_link_not_found(self, db, session_service):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_unlink_tenant_idp(
                request, str(uuid.uuid4()), str(uuid.uuid4()), db, session_service
            )
        mock_sr.assert_called_with("/organisations", error="Identity provider link not found")

    async def test_success(self, db, session_service):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        fed_identity = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=fed_identity))

        request = _mock_request(cookies={"session": "good"})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.settings_redirect") as mock_sr,
        ):
            mock_sr.return_value = MagicMock(status_code=303)
            await settings_unlink_tenant_idp(
                request, str(uuid.uuid4()), str(uuid.uuid4()), db, session_service
            )
        mock_sr.assert_called_with(
            "/organisations", success="Identity provider unlinked successfully"
        )
        db.delete.assert_awaited_once_with(fed_identity)
        db.commit.assert_awaited_once()


class TestGenerateTenantSlug:
    """Tests for generate_tenant_slug()."""

    def test_simple_name(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        assert generate_tenant_slug("Acme Inc") == "acme-inc"

    def test_special_characters(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        assert generate_tenant_slug("My@Company!") == "my-company"

    def test_empty_slug_fallback(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        assert generate_tenant_slug("!!!") == "org"

    def test_long_name_truncated(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        slug = generate_tenant_slug("a" * 100)
        assert len(slug) <= 50

    def test_leading_trailing_hyphens_stripped(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        result = generate_tenant_slug("---test---")
        assert not result.startswith("-")
        assert not result.endswith("-")


# ---------------------------------------------------------------------------
# 9. API Helper: get_token_service
# ---------------------------------------------------------------------------


class TestGetTokenService:
    """Tests for get_token_service()."""

    def test_creates_token_service(self):
        from auth.api.routes.auth.settings import get_token_service

        jwks = MagicMock()
        with patch(f"{MODULE}.TokenService") as MockTS:
            MockTS.return_value = MagicMock()
            get_token_service(jwks)
        MockTS.assert_called_once_with(jwks)


# ---------------------------------------------------------------------------
# 10. Organization Owner Management helpers
# ---------------------------------------------------------------------------


class TestOrgRedirect:
    """Tests for org_redirect()."""

    def test_basic_redirect(self):
        from auth.api.routes.auth.settings import org_redirect

        tid = str(uuid.uuid4())
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            resp = org_redirect(tid, "/edit")
        assert resp.status_code == status.HTTP_303_SEE_OTHER
        assert f"/auth/settings/org/{tid}/edit" in resp.headers["location"]

    def test_with_query_params(self):
        from auth.api.routes.auth.settings import org_redirect

        tid = str(uuid.uuid4())
        with patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            resp = org_redirect(tid, "", success="done")
        assert "success=done" in resp.headers["location"]


class TestRequireTenantManager:
    """Tests for require_tenant_manager()."""

    async def test_no_session_raises(self, db, session_service):
        from auth.api.routes.auth.settings import require_tenant_manager

        request = _mock_request(cookies={})
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_tenant_manager(
                request, str(uuid.uuid4()), db, session_service, required_scope="settings:read"
            )
        assert exc_info.value.status_code == 401

    async def test_invalid_session_raises(self, db, session_service):
        from auth.api.routes.auth.settings import require_tenant_manager

        request = _mock_request(cookies={"session": "bad"})
        session_service.get_user_by_session_token = AsyncMock(return_value=None)
        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_tenant_manager(
                request, str(uuid.uuid4()), db, session_service, required_scope="settings:read"
            )
        assert exc_info.value.status_code == 401

    async def test_invalid_tenant_id_raises(self, db, session_service):
        from auth.api.routes.auth.settings import require_tenant_manager

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_tenant_manager(
                request, "not-a-uuid", db, session_service, required_scope="settings:read"
            )
        assert exc_info.value.status_code == 404

    async def test_tenant_not_found_raises(self, db, session_service):
        from auth.api.routes.auth.settings import require_tenant_manager

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_tenant_manager(
                request, str(uuid.uuid4()), db, session_service, required_scope="settings:read"
            )
        assert exc_info.value.status_code == 404

    async def test_not_a_member_raises(self, db, session_service):
        from auth.api.routes.auth.settings import require_tenant_manager

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        tenant = MagicMock()
        tenant.members = []  # User is not a member
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_tenant_manager(
                request, str(uuid.uuid4()), db, session_service, required_scope="settings:read"
            )
        assert exc_info.value.status_code == 403

    async def test_member_without_scope_raises(self, db, session_service):
        from auth.api.routes.auth.settings import require_tenant_manager

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        membership = MagicMock()
        membership.user_id = user.id
        membership.has_scope.return_value = False

        tenant = MagicMock()
        tenant.members = [membership]
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        request = _mock_request(cookies={"session": "good"})

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_tenant_manager(
                request, str(uuid.uuid4()), db, session_service, required_scope="settings:read"
            )
        assert exc_info.value.status_code == 403

    async def test_authorized_returns_tuple(self, db, session_service):
        from auth.api.routes.auth.settings import require_tenant_manager

        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        membership = MagicMock()
        membership.user_id = user.id
        membership.has_scope.return_value = True

        tenant = MagicMock()
        tenant.members = [membership]
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        request = _mock_request(cookies={"session": "good"})

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await require_tenant_manager(
                request, str(uuid.uuid4()), db, session_service, required_scope="settings:read"
            )
        assert result == (user, tenant, membership)


# ---------------------------------------------------------------------------
# 11. Converter helpers
# ---------------------------------------------------------------------------


class TestOrgBrandingToDict:
    """Tests for org_branding_to_dict()."""

    def test_none_returns_none(self):
        from auth.api.routes.auth.settings import org_branding_to_dict

        assert org_branding_to_dict(None) is None

    def test_converts_branding(self):
        from auth.api.routes.auth.settings import org_branding_to_dict

        branding = MagicMock()
        branding.id = uuid.uuid4()
        branding.tenant_id = uuid.uuid4()
        branding.logo_url = "https://example.com/logo.png"
        branding.logo_dark_url = None
        branding.favicon_url = None
        branding.primary_color = "#000"
        branding.secondary_color = None
        branding.accent_color = None
        branding.background_color = None
        branding.surface_color = None
        branding.text_color = None
        branding.text_muted_color = None
        branding.error_color = None
        branding.success_color = None
        branding.border_color = None
        branding.warning_color = None
        branding.info_color = None
        branding.font_family = None
        branding.font_url = None
        branding.custom_css = None
        branding.custom_js = None
        branding.show_powered_by = True
        branding.created_at = datetime.now(UTC)
        branding.updated_at = None

        result = org_branding_to_dict(branding)
        assert result is not None
        assert result["logo_url"] == "https://example.com/logo.png"
        assert result["primary_color"] == "#000"


class TestOrgMemberToDict:
    """Tests for org_member_to_dict()."""

    def test_converts_member(self):
        from auth.api.routes.auth.settings import org_member_to_dict

        member = MagicMock()
        member.id = uuid.uuid4()
        member.user_id = uuid.uuid4()
        member.role_name = "admin"
        member.role_id = uuid.uuid4()
        member.role_display_name = "Admin"
        member.has_scope.return_value = False
        member.joined_at = datetime.now(UTC)
        member.invited_at = None
        member.created_at = datetime.now(UTC)
        member.user = MagicMock()
        member.user.profile = MagicMock()
        member.user.profile.name = "John"

        result = org_member_to_dict(member, "john@example.com")
        assert result["user_email"] == "john@example.com"
        assert result["role"] == "admin"
        assert result["user_name"] == "John"


class TestOrgTemplateToDict:
    """Tests for org_template_to_dict()."""

    def test_converts_template(self):
        from auth.api.routes.auth.settings import org_template_to_dict

        template = MagicMock()
        template.id = uuid.uuid4()
        template.tenant_id = uuid.uuid4()
        template.template_name = "login"
        template.content = "<html></html>"
        template.is_active = True
        template.description = "Login page"
        template.created_at = datetime.now(UTC)
        template.updated_at = None

        result = org_template_to_dict(template)
        assert result["template_name"] == "login"
        assert result["is_active"] is True
