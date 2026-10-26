# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for admin HTML pages: users_pages.py and roles_pages.py."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from tests.conftest import make_execute_result

USERS_PAGES_MODULE = "auth.api.routes.admin.users_pages"
ROLES_PAGES_MODULE = "auth.api.routes.admin.roles_pages"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_auth():
    """Create a standard auth tuple (user, roles)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    role = MagicMock()
    role.name = "super_admin"
    role.is_system = True
    role.get_all_scope_names.return_value = ["*"]
    role.has_scope.return_value = True
    return (user, [role])


def _make_request(query_params=None):
    """Create a mock FastAPI Request object."""
    request = MagicMock()
    params = query_params or {}
    # Use a MagicMock for query_params to avoid dict attribute conflicts
    qp = MagicMock()
    qp.get = lambda key, default=None: params.get(key, default)
    qp.__getitem__ = lambda self, key: params[key]
    qp.__contains__ = lambda self, key: key in params
    request.query_params = qp
    return request


def _make_templates_mock():
    """Create a mock for get_templates() that returns a mock TemplateResponse."""
    templates = MagicMock()
    mock_response = MagicMock()
    templates.TemplateResponse.return_value = mock_response
    return templates


def _make_user_with_emails_and_profile(
    user_id=None,
    is_active=True,
    with_profile=True,
    with_emails=True,
    email="user@example.com",
    email_verified=True,
    registration_source=None,
    registration_client_id=None,
    registration_tenant_id=None,
):
    """Create a mock User with emails, profile, and registration info."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.is_active = is_active
    user.created_at = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
    user.registration_source = registration_source
    user.registration_client_id = registration_client_id
    user.registration_tenant_id = registration_tenant_id

    if with_emails:
        email_obj = MagicMock()
        email_obj.email = email
        email_obj.is_primary = True
        email_obj.is_verified = email_verified
        email_obj.verified_at = (
            datetime(2025, 1, 15, 10, 5, 0, tzinfo=UTC) if email_verified else None
        )
        user.emails = [email_obj]
    else:
        user.emails = []

    if with_profile:
        profile = MagicMock()
        profile.name = "Test User"
        profile.given_name = "Test"
        profile.family_name = "User"
        profile.middle_name = None
        profile.nickname = "tester"
        profile.preferred_username = "testuser"
        profile.picture_url = "https://example.com/pic.jpg"
        profile.profile_url = "https://example.com/profile"
        profile.website = "https://example.com"
        profile.gender = None
        profile.birthdate = None
        profile.zoneinfo = None
        profile.locale = None
        profile.phone_number = None
        profile.address_street = None
        profile.address_locality = None
        profile.address_region = None
        profile.address_postal_code = None
        profile.address_country = None
        user.profile = profile
    else:
        user.profile = None

    return user


def _make_role(
    role_id=None,
    name="test_role",
    description="A test role",
    is_system=False,
    scope_names=None,
):
    """Create a mock Role model with role_scopes populated."""
    role = MagicMock()
    role.id = role_id or uuid.uuid4()
    role.name = name
    role.description = description
    role.is_system = is_system
    role.created_at = datetime.now(UTC)
    role.updated_at = datetime.now(UTC)

    if scope_names is None:
        scope_names = []
    role_scopes = []
    for sn in scope_names:
        rs = MagicMock()
        rs.scope = MagicMock()
        rs.scope.id = uuid.uuid4()
        rs.scope.name = sn
        rs.scope.description = f"Description for {sn}"
        rs.scope.category = "admin"
        rs.scope.is_active = True
        role_scopes.append(rs)
    role.role_scopes = role_scopes

    role.get_all_scope_names.return_value = scope_names
    role.has_scope.return_value = True

    return role


def _make_scope(
    scope_id=None,
    name="users:read",
    description="Read users",
    resource="users",
    action="read",
    category="admin",
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
    scope.is_active = is_active
    return scope


def _make_user_role(user_id=None, role_id=None, expires_at=None, is_expired=False):
    """Create a mock UserRole model."""
    ur = MagicMock()
    ur.id = uuid.uuid4()
    ur.user_id = user_id or uuid.uuid4()
    ur.role_id = role_id or uuid.uuid4()
    ur.expires_at = expires_at
    ur.is_expired = is_expired
    ur.created_at = datetime.now(UTC)
    return ur


def _mock_permissions():
    """Return a standard permissions dict."""
    return {
        "users:read": True,
        "users:write": True,
        "users:delete": True,
        "users:disable": True,
        "roles:read": True,
        "roles:write": True,
        "roles:delete": True,
        "roles:assign": True,
    }


# ===========================================================================
# USERS PAGES: user_to_dict TESTS
# ===========================================================================


class TestUserToDict:
    """Tests for users_pages.user_to_dict helper."""

    def test_with_profile_and_emails(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile()
        result = user_to_dict(user)

        assert result["id"] == str(user.id)
        assert result["is_active"] is True
        assert result["email"] == "user@example.com"
        assert result["email_verified"] is True
        assert result["profile"] is not None
        assert result["profile"]["name"] == "Test User"
        assert result["profile"]["given_name"] == "Test"
        assert result["profile"]["family_name"] == "User"
        assert result["profile"]["nickname"] == "tester"
        assert result["created_at"] is not None
        assert result["updated_at"] is not None

    def test_without_profile(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile(with_profile=False)
        result = user_to_dict(user)

        assert result["profile"] is None
        assert result["email"] == "user@example.com"

    def test_without_emails(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile(with_emails=False)
        result = user_to_dict(user)

        assert result["email"] is None
        assert result["email_verified"] is False

    def test_unverified_email(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile(email_verified=False)
        result = user_to_dict(user)

        assert result["email"] == "user@example.com"
        assert result["email_verified"] is False

    def test_created_at_none(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile()
        user.created_at = None
        result = user_to_dict(user)

        assert result["created_at"] is None

    def test_updated_at_none(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile()
        user.updated_at = None
        result = user_to_dict(user)

        assert result["updated_at"] is None

    def test_registration_fields(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        tenant_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(
            registration_source="google",
            registration_client_id="client123",
            registration_tenant_id=tenant_id,
        )
        result = user_to_dict(user)

        assert result["registration_source"] == "google"
        assert result["registration_client_id"] == "client123"
        assert result["registration_tenant_id"] == str(tenant_id)

    def test_registration_tenant_id_none(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile(registration_tenant_id=None)
        result = user_to_dict(user)

        assert result["registration_tenant_id"] is None

    def test_multiple_emails_picks_primary(self):
        from auth.api.routes.admin.users_pages import user_to_dict

        user = _make_user_with_emails_and_profile(with_emails=False)
        email1 = MagicMock()
        email1.email = "secondary@example.com"
        email1.is_primary = False
        email1.is_verified = True
        email2 = MagicMock()
        email2.email = "primary@example.com"
        email2.is_primary = True
        email2.is_verified = True
        user.emails = [email1, email2]

        result = user_to_dict(user)

        assert result["email"] == "primary@example.com"
        assert result["email_verified"] is True


# ===========================================================================
# USERS PAGES: service stubs
# ===========================================================================


def _patch_user_service(users=None, total=0, user=None, email_exists=False):
    """Return a MagicMock replacement for ``_user_service``."""
    service = MagicMock()
    service.list = AsyncMock(return_value=(users or [], total))
    service.get_by_id = AsyncMock(return_value=user)
    service.email_exists = AsyncMock(return_value=email_exists)
    service.create_admin_user = AsyncMock(return_value=user)
    service.delete = AsyncMock()
    return service


def _patch_tenant_service(dropdown=None, memberships=None, display_name=None):
    """Return a MagicMock replacement for ``_tenant_service``."""
    service = MagicMock()
    service.list_active_dropdown = AsyncMock(return_value=dropdown or [])
    service.list_user_memberships = AsyncMock(return_value=memberships or [])
    service.get_display_name = AsyncMock(return_value=display_name)
    return service


# ===========================================================================
# USERS PAGES: users_list_page TESTS
# ===========================================================================


class TestUsersListPage:
    """Tests for users_list_page."""

    async def test_basic_list(self, db):
        from auth.api.routes.admin.users_pages import users_list_page

        user1 = _make_user_with_emails_and_profile(email="a@example.com")
        user2 = _make_user_with_emails_and_profile(email="b@example.com")

        user_service = _patch_user_service(users=[user1, user2], total=2)
        tenant_service = _patch_tenant_service()

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await users_list_page(
                request=request,
                db=db,
                auth=auth,
                page=1,
                search=None,
                is_active=None,
                registration_tenant=None,
            )

        mock_templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")

        assert context["active_section"] == "users"
        assert context["total"] == 2
        assert context["page"] == 1
        assert len(context["users"]) == 2

    async def _call_list(self, db, **page_kwargs):
        """Shared helper invoking ``users_list_page`` with common stubs."""
        from auth.api.routes.admin.users_pages import users_list_page

        user_service = _patch_user_service(
            users=page_kwargs.pop("users", []),
            total=page_kwargs.pop("total", 0),
        )
        tenant_service = _patch_tenant_service(dropdown=page_kwargs.pop("dropdown", []))
        request = page_kwargs.pop("request", _make_request())
        auth = page_kwargs.pop("auth", _make_auth())
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await users_list_page(
                request=request,
                db=db,
                auth=auth,
                **page_kwargs,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        return (
            call_kwargs.kwargs.get("context") or call_kwargs[1].get("context"),
            user_service,
            tenant_service,
        )

    async def test_list_with_search(self, db):
        context, user_service, _ = await self._call_list(
            db,
            page=1,
            search="nonexistent",
            is_active=None,
            registration_tenant=None,
        )
        assert context["search"] == "nonexistent"
        assert context["total"] == 0
        user_service.list.assert_awaited_once()
        assert user_service.list.await_args.kwargs["search"] == "nonexistent"

    async def test_list_with_active_filter_true(self, db):
        context, user_service, _ = await self._call_list(
            db,
            users=[_make_user_with_emails_and_profile()],
            total=1,
            page=1,
            search=None,
            is_active="true",
            registration_tenant=None,
        )
        assert context["is_active"] == "true"
        assert user_service.list.await_args.kwargs["is_active"] is True

    async def test_list_with_active_filter_false(self, db):
        context, user_service, _ = await self._call_list(
            db,
            page=1,
            search=None,
            is_active="false",
            registration_tenant=None,
        )
        assert context["is_active"] == "false"
        assert user_service.list.await_args.kwargs["is_active"] is False

    async def test_list_with_tenant_filter_none(self, db):
        context, user_service, _ = await self._call_list(
            db,
            page=1,
            search=None,
            is_active=None,
            registration_tenant="none",
        )
        assert context["registration_tenant"] == "none"
        assert user_service.list.await_args.kwargs["filter_no_tenant"] is True

    async def test_list_with_tenant_filter_uuid(self, db):
        tenant_id = uuid.uuid4()
        context, user_service, _ = await self._call_list(
            db,
            page=1,
            search=None,
            is_active=None,
            registration_tenant=str(tenant_id),
        )
        assert context["registration_tenant"] == str(tenant_id)
        assert user_service.list.await_args.kwargs["registration_tenant_id"] == tenant_id

    async def test_list_with_invalid_tenant_uuid(self, db):
        """Invalid tenant UUID is silently ignored."""
        context, user_service, _ = await self._call_list(
            db,
            page=1,
            search=None,
            is_active=None,
            registration_tenant="invalid-uuid",
        )
        assert user_service.list.await_args.kwargs["registration_tenant_id"] is None

    async def test_list_with_success_and_error_query_params(self, db):
        context, _, _ = await self._call_list(
            db,
            request=_make_request({"success": "Done", "error": "Oops"}),
            page=1,
            search=None,
            is_active=None,
            registration_tenant=None,
        )
        assert context["success"] == "Done"
        assert context["error"] == "Oops"

    async def test_list_pagination(self, db):
        context, _, _ = await self._call_list(
            db,
            total=45,
            page=3,
            search=None,
            is_active=None,
            registration_tenant=None,
        )
        assert context["page"] == 3
        assert context["total"] == 45
        assert context["total_pages"] == 3  # ceil(45/20) = 3

    async def test_list_tenants_loaded(self, db):
        tenant_id = uuid.uuid4()
        context, _, tenant_service = await self._call_list(
            db,
            dropdown=[(tenant_id, "My Tenant", "my-tenant")],
            page=1,
            search=None,
            is_active=None,
            registration_tenant=None,
        )
        assert len(context["tenants"]) == 1
        assert context["tenants"][0]["name"] == "My Tenant"
        assert context["tenants"][0]["slug"] == "my-tenant"
        tenant_service.list_active_dropdown.assert_awaited_once()


# ===========================================================================
# USERS PAGES: user_create_page TESTS
# ===========================================================================


class TestUserCreatePage:
    """Tests for user_create_page."""

    async def test_create_form_renders(self, db):
        from auth.api.routes.admin.users_pages import user_create_page

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_create_page(request=request, auth=auth)

        mock_templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["active_section"] == "users"

    async def test_create_form_with_error(self, db):
        from auth.api.routes.admin.users_pages import user_create_page

        request = _make_request({"error": "Something went wrong"})
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_create_page(request=request, auth=auth)

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["error"] == "Something went wrong"


# ===========================================================================
# USERS PAGES: user_create_submit TESTS
# ===========================================================================


class TestUserCreateSubmit:
    """Tests for user_create_submit."""

    async def test_create_success(self, db):
        from auth.api.routes.admin.users_pages import user_create_submit

        created_user = MagicMock()
        created_user.id = uuid.uuid4()
        user_service = _patch_user_service(user=created_user, email_exists=False)

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_create_submit(
                request=request,
                db=db,
                auth=auth,
                email="new@example.com",
                password="securepass123",
                name="Test User",
                is_verified="true",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=User+created" in result.headers.get("location", "")
        user_service.create_admin_user.assert_awaited_once()
        kwargs = user_service.create_admin_user.await_args.kwargs
        assert kwargs["email"] == "new@example.com"
        assert kwargs["is_verified"] is True

    async def test_create_with_short_password(self, db):
        from auth.api.routes.admin.users_pages import user_create_submit

        request = _make_request()
        auth = _make_auth()

        result = await user_create_submit(
            request=request,
            db=db,
            auth=auth,
            email="new@example.com",
            password="short",
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Password" in result.headers.get("location", "")

    async def test_create_duplicate_email(self, db):
        from auth.api.routes.admin.users_pages import user_create_submit

        user_service = _patch_user_service(email_exists=True)

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_create_submit(
                request=request,
                db=db,
                auth=auth,
                email="exists@example.com",
                password="securepass123",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Email+already" in result.headers.get("location", "")

    async def test_create_without_name(self, db):
        from auth.api.routes.admin.users_pages import user_create_submit

        created_user = MagicMock()
        created_user.id = uuid.uuid4()
        user_service = _patch_user_service(user=created_user, email_exists=False)

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_create_submit(
                request=request,
                db=db,
                auth=auth,
                email="noname@example.com",
                password="securepass123",
                name=None,
                is_verified=None,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers.get("location", "")
        assert user_service.create_admin_user.await_args.kwargs["name"] is None

    async def test_create_exception_redirects_with_error(self, db):
        from auth.api.routes.admin.users_pages import user_create_submit

        user_service = _patch_user_service(email_exists=False)
        user_service.create_admin_user = AsyncMock(side_effect=Exception("DB error"))

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_create_submit(
                request=request,
                db=db,
                auth=auth,
                email="fail@example.com",
                password="securepass123",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=" in result.headers.get("location", "")


# ===========================================================================
# USERS PAGES: user_edit_page TESTS
# ===========================================================================


class TestUserEditPage:
    """Tests for user_edit_page."""

    async def test_edit_form_renders(self, db):
        from auth.api.routes.admin.users_pages import user_edit_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_edit_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        mock_templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["active_section"] == "users"
        assert context["user"]["id"] == str(user_id)

    async def test_edit_form_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_edit_page

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await user_edit_page(
                request=request,
                user_id="bad-uuid",
                db=db,
                auth=auth,
            )
        assert exc_info.value.status_code == 400

    async def test_edit_form_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_edit_page

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)

        request = _make_request()
        auth = _make_auth()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            pytest.raises(HTTPException) as exc_info,
        ):
            await user_edit_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
            )
        assert exc_info.value.status_code == 404

    async def test_edit_form_with_error_and_success(self, db):
        from auth.api.routes.admin.users_pages import user_edit_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)

        request = _make_request({"error": "Err", "success": "OK"})
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_edit_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["error"] == "Err"
        assert context["success"] == "OK"


# ===========================================================================
# USERS PAGES: user_edit_submit TESTS
# ===========================================================================


class TestUserEditSubmit:
    """Tests for user_edit_submit."""

    async def test_edit_success(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)
        profile_service = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_edit_submit(
                request=request,
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                name="Updated Name",
                given_name="Updated",
                is_active="true",
                is_verified="true",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=User+updated" in result.headers.get("location", "")

    async def test_edit_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        request = _make_request()
        auth = _make_auth()
        profile_service = AsyncMock()

        result = await user_edit_submit(
            request=request,
            user_id="bad-uuid",
            db=db,
            profile_service=profile_service,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers.get("location", "")

    async def test_edit_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)
        profile_service = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_edit_submit(
                request=request,
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+not+found" in result.headers.get("location", "")

    async def test_edit_creates_profile_if_missing(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id, with_profile=False)
        user_service = _patch_user_service(user=user)
        profile_service = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_edit_submit(
                request=request,
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                name="New Name",
                is_active="true",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        # profile_service.add_profile should have been called to stage the new profile
        profile_service.add_profile.assert_awaited()

    async def test_edit_auto_generates_name_from_parts(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)
        profile_service = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_edit_submit(
                request=request,
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                name="",
                given_name="John",
                family_name="Doe",
                is_active="true",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        # The profile.name should be auto-generated from given/family
        assert user.profile.name == "John Doe"

    async def test_edit_changes_active_status(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id, is_active=True)
        user_service = _patch_user_service(user=user)
        profile_service = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            await user_edit_submit(
                request=request,
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                is_active="false",
            )

        assert user.is_active is False

    async def test_edit_changes_verification_status(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id, email_verified=False)
        user_service = _patch_user_service(user=user)
        profile_service = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            await user_edit_submit(
                request=request,
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                is_verified="true",
                is_active="true",
            )

        primary_email = user.emails[0]
        assert primary_email.is_verified is True
        assert primary_email.verified_at is not None

    async def test_edit_exception_redirects_with_error(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)
        profile_service = AsyncMock()

        db.commit = AsyncMock(side_effect=Exception("DB error"))

        request = _make_request()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_edit_submit(
                request=request,
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                name="Test",
                is_active="true",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=" in result.headers.get("location", "")


# ===========================================================================
# USERS PAGES: user_avatar_upload TESTS
# ===========================================================================


class TestUserAvatarUpload:
    """Tests for user_avatar_upload."""

    async def test_avatar_upload_success(self, db):
        from auth.api.routes.admin.users_pages import user_avatar_upload

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)

        avatar = MagicMock()
        profile_service = AsyncMock()
        auth = _make_auth()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}.upload_service") as mock_upload,
        ):
            mock_upload.save_avatar = AsyncMock(return_value="avatars/test.jpg")
            mock_upload.get_avatar_url.return_value = "https://cdn.example.com/avatars/test.jpg"

            result = await user_avatar_upload(
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                avatar=avatar,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Avatar+uploaded" in result.headers.get("location", "")

    async def test_avatar_upload_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_avatar_upload

        avatar = MagicMock()
        profile_service = AsyncMock()
        auth = _make_auth()

        result = await user_avatar_upload(
            user_id="bad-uuid",
            db=db,
            profile_service=profile_service,
            auth=auth,
            avatar=avatar,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers.get("location", "")

    async def test_avatar_upload_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_avatar_upload

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)

        avatar = MagicMock()
        profile_service = AsyncMock()
        auth = _make_auth()

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_avatar_upload(
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                avatar=avatar,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+not+found" in result.headers.get("location", "")

    async def test_avatar_upload_error(self, db):
        from auth.api.routes.admin.users_pages import user_avatar_upload
        from auth.services.upload import UploadError

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)

        avatar = MagicMock()
        profile_service = AsyncMock()
        auth = _make_auth()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}.upload_service") as mock_upload,
        ):
            mock_upload.save_avatar = AsyncMock(side_effect=UploadError("File too large"))

            result = await user_avatar_upload(
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                avatar=avatar,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        location = result.headers.get("location", "")
        assert "error=File" in location and "too" in location and "large" in location

    async def test_avatar_upload_generic_exception(self, db):
        from auth.api.routes.admin.users_pages import user_avatar_upload

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)
        user_service = _patch_user_service(user=user)

        avatar = MagicMock()
        profile_service = AsyncMock()
        auth = _make_auth()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}.upload_service") as mock_upload,
        ):
            mock_upload.save_avatar = AsyncMock(side_effect=Exception("Unexpected error"))

            result = await user_avatar_upload(
                user_id=str(user_id),
                db=db,
                profile_service=profile_service,
                auth=auth,
                avatar=avatar,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Failed+to+upload+avatar" in result.headers.get("location", "")


# ===========================================================================
# USERS PAGES: user_detail_page TESTS
# ===========================================================================


def _mk_session_service(session_count=0):
    svc = MagicMock()
    svc.count_active = AsyncMock(return_value=session_count)
    svc.revoke_all_active_sessions = AsyncMock(return_value=session_count)
    return svc


def _mk_mfa_service(user_mfa=None):
    svc = MagicMock()
    svc.get_user_mfa = AsyncMock(return_value=user_mfa)
    return svc


def _mk_oauth2_client_service(client=None):
    svc = MagicMock()
    svc.get_client_by_client_id = AsyncMock(return_value=client)
    return svc


class TestUserDetailPage:
    """Tests for user_detail_page."""

    async def test_detail_without_mfa(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)

        user_service = _patch_user_service(user=user)
        tenant_service = _patch_tenant_service(memberships=[])
        session_service = _mk_session_service(session_count=2)
        mfa_service = _mk_mfa_service(user_mfa=None)
        oauth2_client_service = _mk_oauth2_client_service()

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=session_service,
                mfa_service=mfa_service,
                oauth2_client_service=oauth2_client_service,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["user"]["mfa"]["totp_enabled"] is False
        assert context["user"]["active_sessions"] == 2
        assert context["user"]["tenant_memberships"] == []

    async def test_detail_with_mfa(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)

        mfa = MagicMock()
        mfa.id = uuid.uuid4()
        mfa.totp_enabled = True
        mfa.totp_enabled_at = datetime(2025, 2, 1, tzinfo=UTC)
        # 5 unused backup codes
        mfa.backup_codes = []
        for _ in range(5):
            code = MagicMock()
            code.used_at = None
            mfa.backup_codes.append(code)

        user_service = _patch_user_service(user=user)
        tenant_service = _patch_tenant_service(memberships=[])
        session_service = _mk_session_service(session_count=1)
        mfa_service = _mk_mfa_service(user_mfa=mfa)
        oauth2_client_service = _mk_oauth2_client_service()

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=session_service,
                mfa_service=mfa_service,
                oauth2_client_service=oauth2_client_service,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["user"]["mfa"]["totp_enabled"] is True
        assert context["user"]["mfa"]["backup_codes_remaining"] == 5

    async def test_detail_with_tenant_memberships(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)

        tenant_id = uuid.uuid4()
        tenant = MagicMock()
        tenant.id = tenant_id
        tenant.display_name = "Acme"
        tenant.slug = "acme"
        tenant.is_active = True

        membership = MagicMock()
        membership.tenant_id = tenant_id
        membership.tenant = tenant
        membership.role_display_name = "Admin"
        membership.joined_at = datetime(2025, 2, 1, tzinfo=UTC)

        user_service = _patch_user_service(user=user)
        tenant_service = _patch_tenant_service(memberships=[membership])
        session_service = _mk_session_service()
        mfa_service = _mk_mfa_service()
        oauth2_client_service = _mk_oauth2_client_service()

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=session_service,
                mfa_service=mfa_service,
                oauth2_client_service=oauth2_client_service,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        memberships = context["user"]["tenant_memberships"]
        assert len(memberships) == 1
        assert memberships[0]["tenant_name"] == "Acme"
        assert memberships[0]["role"] == "Admin"

    async def test_detail_with_registration_client(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(
            user_id=user_id,
            registration_client_id="client123",
        )

        client = MagicMock()
        client.name = "My App"

        user_service = _patch_user_service(user=user)
        tenant_service = _patch_tenant_service(memberships=[])
        session_service = _mk_session_service()
        mfa_service = _mk_mfa_service()
        oauth2_client_service = _mk_oauth2_client_service(client=client)

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=session_service,
                mfa_service=mfa_service,
                oauth2_client_service=oauth2_client_service,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["user"]["registration_client_name"] == "My App"

    async def test_detail_with_registration_tenant(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(
            user_id=user_id,
            registration_tenant_id=tenant_id,
        )

        user_service = _patch_user_service(user=user)
        tenant_service = _patch_tenant_service(memberships=[], display_name="My Tenant")
        session_service = _mk_session_service()
        mfa_service = _mk_mfa_service()
        oauth2_client_service = _mk_oauth2_client_service()

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=session_service,
                mfa_service=mfa_service,
                oauth2_client_service=oauth2_client_service,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["user"]["registration_tenant_name"] == "My Tenant"

    async def test_detail_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await user_detail_page(
                request=request,
                user_id="not-valid",
                db=db,
                auth=auth,
                session_service=_mk_session_service(),
                mfa_service=_mk_mfa_service(),
                oauth2_client_service=_mk_oauth2_client_service(),
            )
        assert exc_info.value.status_code == 400

    async def test_detail_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)

        request = _make_request()
        auth = _make_auth()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            pytest.raises(HTTPException) as exc_info,
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=_mk_session_service(),
                mfa_service=_mk_mfa_service(),
                oauth2_client_service=_mk_oauth2_client_service(),
            )
        assert exc_info.value.status_code == 404

    async def test_detail_with_success_and_error(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)

        user_service = _patch_user_service(user=user)
        tenant_service = _patch_tenant_service(memberships=[])

        request = _make_request({"success": "Done", "error": "Oops"})
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=_mk_session_service(),
                mfa_service=_mk_mfa_service(),
                oauth2_client_service=_mk_oauth2_client_service(),
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["success"] == "Done"
        assert context["error"] == "Oops"

    async def test_detail_emails_serialized(self, db):
        from auth.api.routes.admin.users_pages import user_detail_page

        user_id = uuid.uuid4()
        user = _make_user_with_emails_and_profile(user_id=user_id)

        user_service = _patch_user_service(user=user)
        tenant_service = _patch_tenant_service(memberships=[])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{USERS_PAGES_MODULE}._user_service", user_service),
            patch(f"{USERS_PAGES_MODULE}._tenant_service", tenant_service),
            patch(f"{USERS_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{USERS_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await user_detail_page(
                request=request,
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=_mk_session_service(),
                mfa_service=_mk_mfa_service(),
                oauth2_client_service=_mk_oauth2_client_service(),
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert "emails" in context["user"]
        assert len(context["user"]["emails"]) == 1
        assert context["user"]["emails"][0]["email"] == "user@example.com"


# ===========================================================================
# USERS PAGES: user_disable_submit TESTS
# ===========================================================================


class TestUserDisableSubmit:
    """Tests for user_disable_submit."""

    async def test_disable_success(self, db):
        from auth.api.routes.admin.users_pages import user_disable_submit

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user.is_active = True
        user_service = _patch_user_service(user=user)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_disable_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=User+disabled" in result.headers.get("location", "")
        assert user.is_active is False

    async def test_disable_already_disabled(self, db):
        from auth.api.routes.admin.users_pages import user_disable_submit

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user.is_active = False
        user_service = _patch_user_service(user=user)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_disable_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+already+disabled" in result.headers.get("location", "")

    async def test_disable_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_disable_submit

        auth = _make_auth()
        result = await user_disable_submit(
            user_id="bad-uuid",
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers.get("location", "")

    async def test_disable_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_disable_submit

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_disable_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+not+found" in result.headers.get("location", "")


# ===========================================================================
# USERS PAGES: user_enable_submit TESTS
# ===========================================================================


class TestUserEnableSubmit:
    """Tests for user_enable_submit."""

    async def test_enable_success(self, db):
        from auth.api.routes.admin.users_pages import user_enable_submit

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user.is_active = False
        user_service = _patch_user_service(user=user)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_enable_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=User+enabled" in result.headers.get("location", "")
        assert user.is_active is True

    async def test_enable_already_enabled(self, db):
        from auth.api.routes.admin.users_pages import user_enable_submit

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user.is_active = True
        user_service = _patch_user_service(user=user)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_enable_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+already+enabled" in result.headers.get("location", "")

    async def test_enable_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_enable_submit

        auth = _make_auth()
        result = await user_enable_submit(
            user_id="bad",
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers.get("location", "")

    async def test_enable_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_enable_submit

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_enable_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+not+found" in result.headers.get("location", "")


# ===========================================================================
# USERS PAGES: user_revoke_sessions_submit TESTS
# ===========================================================================


class TestUserRevokeSessionsSubmit:
    """Tests for user_revoke_sessions_submit."""

    async def test_revoke_sessions_success(self, db):
        from auth.api.routes.admin.users_pages import user_revoke_sessions_submit

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id

        user_service = _patch_user_service(user=user)
        session_service = _mk_session_service(session_count=2)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_revoke_sessions_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=session_service,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Revoked+2+session" in result.headers.get("location", "")
        session_service.revoke_all_active_sessions.assert_awaited_once()

    async def test_revoke_sessions_none_active(self, db):
        from auth.api.routes.admin.users_pages import user_revoke_sessions_submit

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id

        user_service = _patch_user_service(user=user)
        session_service = _mk_session_service(session_count=0)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_revoke_sessions_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=session_service,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Revoked+0+session" in result.headers.get("location", "")

    async def test_revoke_sessions_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_revoke_sessions_submit

        auth = _make_auth()
        result = await user_revoke_sessions_submit(
            user_id="bad",
            db=db,
            auth=auth,
            session_service=_mk_session_service(),
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers.get("location", "")

    async def test_revoke_sessions_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_revoke_sessions_submit

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_revoke_sessions_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
                session_service=_mk_session_service(),
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+not+found" in result.headers.get("location", "")


# ===========================================================================
# USERS PAGES: user_delete_submit TESTS
# ===========================================================================


class TestUserDeleteSubmit:
    """Tests for user_delete_submit."""

    async def test_delete_success(self, db):
        from auth.api.routes.admin.users_pages import user_delete_submit

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user_service = _patch_user_service(user=user)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_delete_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=User+deleted" in result.headers.get("location", "")
        user_service.delete.assert_awaited_once_with(db, user)

    async def test_delete_invalid_uuid(self, db):
        from auth.api.routes.admin.users_pages import user_delete_submit

        auth = _make_auth()
        result = await user_delete_submit(
            user_id="bad",
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+user+ID" in result.headers.get("location", "")

    async def test_delete_user_not_found(self, db):
        from auth.api.routes.admin.users_pages import user_delete_submit

        user_id = uuid.uuid4()
        user_service = _patch_user_service(user=None)

        auth = _make_auth()
        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_delete_submit(
                user_id=str(user_id),
                db=db,
                auth=auth,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+not+found" in result.headers.get("location", "")


# ===========================================================================
# USERS PAGES: users_bulk_delete TESTS
# ===========================================================================


class TestUsersBulkDelete:
    """Tests for users_bulk_delete."""

    async def test_bulk_delete_success(self, db):
        from auth.api.routes.admin.users_pages import users_bulk_delete

        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()
        admin_user = MagicMock()
        admin_user.id = uuid.uuid4()  # different from uid1 and uid2

        user1 = MagicMock()
        user1.id = uid1
        user2 = MagicMock()
        user2.id = uid2

        user_service = MagicMock()
        user_service.get_by_id = AsyncMock(side_effect=[user1, user2])
        user_service.delete = AsyncMock()

        form = MagicMock()
        form.getlist.return_value = [str(uid1), str(uid2)]

        request = MagicMock()
        request.form = AsyncMock(return_value=form)

        auth = (admin_user, [_make_role()])

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await users_bulk_delete(request=request, db=db, auth=auth)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Deleted+2+user" in result.headers.get("location", "")

    async def test_bulk_delete_no_users_selected(self, db):
        from auth.api.routes.admin.users_pages import users_bulk_delete

        form = MagicMock()
        form.getlist.return_value = []

        request = MagicMock()
        request.form = AsyncMock(return_value=form)

        auth = _make_auth()

        result = await users_bulk_delete(request=request, db=db, auth=auth)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=No+users+selected" in result.headers.get("location", "")

    async def test_bulk_delete_skips_admin_user(self, db):
        from auth.api.routes.admin.users_pages import users_bulk_delete

        admin_id = uuid.uuid4()
        admin_user = MagicMock()
        admin_user.id = admin_id

        other_id = uuid.uuid4()
        other_user = MagicMock()
        other_user.id = other_id

        user_service = MagicMock()
        user_service.get_by_id = AsyncMock(return_value=other_user)
        user_service.delete = AsyncMock()

        form = MagicMock()
        form.getlist.return_value = [str(admin_id), str(other_id)]

        request = MagicMock()
        request.form = AsyncMock(return_value=form)

        auth = (admin_user, [_make_role()])

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await users_bulk_delete(request=request, db=db, auth=auth)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Deleted+1+user" in result.headers.get("location", "")

    async def test_bulk_delete_skips_invalid_uuids(self, db):
        from auth.api.routes.admin.users_pages import users_bulk_delete

        admin_user = MagicMock()
        admin_user.id = uuid.uuid4()

        user_service = MagicMock()
        user_service.get_by_id = AsyncMock()
        user_service.delete = AsyncMock()

        form = MagicMock()
        form.getlist.return_value = ["invalid-uuid", "also-bad"]

        request = MagicMock()
        request.form = AsyncMock(return_value=form)

        auth = (admin_user, [_make_role()])

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await users_bulk_delete(request=request, db=db, auth=auth)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Deleted+0+user" in result.headers.get("location", "")

    async def test_bulk_delete_skips_not_found_users(self, db):
        from auth.api.routes.admin.users_pages import users_bulk_delete

        admin_user = MagicMock()
        admin_user.id = uuid.uuid4()

        uid = uuid.uuid4()
        user_service = MagicMock()
        user_service.get_by_id = AsyncMock(return_value=None)
        user_service.delete = AsyncMock()

        form = MagicMock()
        form.getlist.return_value = [str(uid)]

        request = MagicMock()
        request.form = AsyncMock(return_value=form)

        auth = (admin_user, [_make_role()])

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await users_bulk_delete(request=request, db=db, auth=auth)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Deleted+0+user" in result.headers.get("location", "")


# ===========================================================================
# ROLES PAGES: role_to_dict TESTS
# ===========================================================================


class TestRoleToDict:
    """Tests for roles_pages.role_to_dict helper."""

    def test_basic_conversion(self):
        from auth.api.routes.admin.roles_pages import role_to_dict

        role = _make_role(name="editor", description="Edit stuff", scope_names=["users:read"])
        result = role_to_dict(role, user_count=5)

        assert result["name"] == "editor"
        assert result["description"] == "Edit stuff"
        assert result["scopes"] == ["users:read"]
        assert result["user_count"] == 5
        assert result["id"] == str(role.id)
        assert result["is_system"] is False

    def test_default_user_count_zero(self):
        from auth.api.routes.admin.roles_pages import role_to_dict

        role = _make_role()
        result = role_to_dict(role)
        assert result["user_count"] == 0

    def test_created_at_iso(self):
        from auth.api.routes.admin.roles_pages import role_to_dict

        role = _make_role()
        result = role_to_dict(role)
        assert result["created_at"] == role.created_at.isoformat()

    def test_created_at_none(self):
        from auth.api.routes.admin.roles_pages import role_to_dict

        role = _make_role()
        role.created_at = None
        result = role_to_dict(role)
        assert result["created_at"] is None

    def test_updated_at_none(self):
        from auth.api.routes.admin.roles_pages import role_to_dict

        role = _make_role()
        role.updated_at = None
        result = role_to_dict(role)
        assert result["updated_at"] is None

    def test_system_role(self):
        from auth.api.routes.admin.roles_pages import role_to_dict

        role = _make_role(is_system=True)
        result = role_to_dict(role)
        assert result["is_system"] is True


# ===========================================================================
# ROLES PAGES: roles_list_page TESTS
# ===========================================================================


class TestRolesListPage:
    """Tests for roles_list_page."""

    async def test_basic_list(self, db):
        from auth.api.routes.admin.roles_pages import roles_list_page

        role1 = _make_role(name="admin", scope_names=["*"])
        role2 = _make_role(name="viewer", scope_names=["users:read"])

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        roles_result = make_execute_result(scalars_list=[role1, role2])

        uc1 = MagicMock()
        uc1.scalar.return_value = 3
        uc2 = MagicMock()
        uc2.scalar.return_value = 1

        db.execute = AsyncMock(side_effect=[count_result, roles_result, uc1, uc2])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await roles_list_page(
                request=request,
                db=db,
                auth=auth,
                page=1,
                search=None,
                is_system=None,
            )

        mock_templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["active_section"] == "roles"
        assert context["total"] == 2
        assert len(context["roles"]) == 2

    async def test_list_with_search(self, db):
        from auth.api.routes.admin.roles_pages import roles_list_page

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        roles_result = make_execute_result(scalars_list=[])

        db.execute = AsyncMock(side_effect=[count_result, roles_result])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await roles_list_page(
                request=request,
                db=db,
                auth=auth,
                page=1,
                search="admin",
                is_system=None,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["search"] == "admin"

    async def test_list_with_is_system_true(self, db):
        from auth.api.routes.admin.roles_pages import roles_list_page

        role = _make_role(name="admin", is_system=True)

        count_result = MagicMock()
        count_result.scalar.return_value = 1
        roles_result = make_execute_result(scalars_list=[role])
        uc = MagicMock()
        uc.scalar.return_value = 5

        db.execute = AsyncMock(side_effect=[count_result, roles_result, uc])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await roles_list_page(
                request=request,
                db=db,
                auth=auth,
                page=1,
                search=None,
                is_system="true",
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["is_system"] == "true"

    async def test_list_with_is_system_false(self, db):
        from auth.api.routes.admin.roles_pages import roles_list_page

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        roles_result = make_execute_result(scalars_list=[])

        db.execute = AsyncMock(side_effect=[count_result, roles_result])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await roles_list_page(
                request=request,
                db=db,
                auth=auth,
                page=1,
                search=None,
                is_system="false",
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["is_system"] == "false"


# ===========================================================================
# ROLES PAGES: role_create_page TESTS
# ===========================================================================


class TestRoleCreatePage:
    """Tests for role_create_page."""

    async def test_create_form_renders(self, db):
        from auth.api.routes.admin.roles_pages import role_create_page

        scope = _make_scope(name="users:read", category="admin")

        scopes_result = make_execute_result(scalars_list=[scope])
        db.execute = AsyncMock(return_value=scopes_result)

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_create_page(
                request=request,
                db=db,
                auth=auth,
            )

        mock_templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["active_section"] == "roles"
        assert "scopes_by_category" in context

    async def test_create_form_with_error(self, db):
        from auth.api.routes.admin.roles_pages import role_create_page

        scopes_result = make_execute_result(scalars_list=[])
        db.execute = AsyncMock(return_value=scopes_result)

        request = _make_request({"error": "Something bad"})
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_create_page(
                request=request,
                db=db,
                auth=auth,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["error"] == "Something bad"


# ===========================================================================
# ROLES PAGES: role_create_submit TESTS
# ===========================================================================


class TestRoleCreateSubmit:
    """Tests for role_create_submit."""

    async def test_create_success_no_scopes(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        existing_result = make_execute_result(scalar_value=None)
        db.execute = AsyncMock(return_value=existing_result)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        result = await role_create_submit(
            request=request,
            db=db,
            auth=auth,
            name="editor",
            description="Can edit",
            scopes=None,
            wildcard_scopes=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Role+created" in result.headers.get("location", "")

    async def test_create_success_with_scopes(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        scope1 = _make_scope(name="users:read")
        scope2 = _make_scope(name="users:write")

        existing_result = make_execute_result(scalar_value=None)
        scopes_result = make_execute_result(scalars_list=[scope1, scope2])

        db.execute = AsyncMock(side_effect=[existing_result, scopes_result])
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        result = await role_create_submit(
            request=request,
            db=db,
            auth=auth,
            name="editor",
            description=None,
            scopes=["users:read", "users:write"],
            wildcard_scopes=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Role+created" in result.headers.get("location", "")

    async def test_create_duplicate_name(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        existing_role = _make_role(name="editor")
        existing_result = make_execute_result(scalar_value=existing_role)
        db.execute = AsyncMock(return_value=existing_result)

        request = _make_request()
        auth = _make_auth()

        result = await role_create_submit(
            request=request,
            db=db,
            auth=auth,
            name="editor",
            description=None,
            scopes=None,
            wildcard_scopes=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Role+name+already+exists" in result.headers.get("location", "")

    async def test_create_with_invalid_scopes(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        existing_result = make_execute_result(scalar_value=None)
        # Return empty list for scopes lookup (none found in DB)
        scopes_result = make_execute_result(scalars_list=[])

        db.execute = AsyncMock(side_effect=[existing_result, scopes_result])

        request = _make_request()
        auth = _make_auth()

        result = await role_create_submit(
            request=request,
            db=db,
            auth=auth,
            name="editor",
            description=None,
            scopes=["nonexistent:scope"],
            wildcard_scopes=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+scopes" in result.headers.get("location", "")

    async def test_create_with_wildcard_scopes(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        scope = _make_scope(name="custom:thing")

        existing_result = make_execute_result(scalar_value=None)
        scopes_result = make_execute_result(scalars_list=[scope])

        db.execute = AsyncMock(side_effect=[existing_result, scopes_result])
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        request = _make_request()
        auth = _make_auth()

        result = await role_create_submit(
            request=request,
            db=db,
            auth=auth,
            name="custom_role",
            description=None,
            scopes=None,
            wildcard_scopes="custom:thing",
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Role+created" in result.headers.get("location", "")

    async def test_create_exception_redirects_with_error(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        existing_result = make_execute_result(scalar_value=None)
        db.execute = AsyncMock(return_value=existing_result)
        db.flush = AsyncMock(side_effect=Exception("DB error"))

        request = _make_request()
        auth = _make_auth()

        result = await role_create_submit(
            request=request,
            db=db,
            auth=auth,
            name="editor",
            description=None,
            scopes=None,
            wildcard_scopes=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=" in result.headers.get("location", "")


# ===========================================================================
# ROLES PAGES: role_detail_page TESTS
# ===========================================================================


class TestRoleDetailPage:
    """Tests for role_detail_page."""

    async def test_detail_renders(self, db):
        from auth.api.routes.admin.roles_pages import role_detail_page

        role_id = uuid.uuid4()
        role = _make_role(role_id=role_id, name="editor", scope_names=["users:read"])

        role_result = make_execute_result(scalar_value=role)

        # Users with this role
        user = MagicMock()
        user.id = uuid.uuid4()
        user.is_active = True
        user_email = MagicMock()
        user_email.email = "user@example.com"
        user_role = _make_user_role(user_id=user.id, role_id=role_id)

        users_result = MagicMock()
        users_result.all.return_value = [(user_role, user, user_email)]

        # Available scopes
        scope = _make_scope(name="users:read")
        scopes_result = make_execute_result(scalars_list=[scope])

        db.execute = AsyncMock(side_effect=[role_result, users_result, scopes_result])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_detail_page(
                request=request,
                role_id=str(role_id),
                db=db,
                auth=auth,
            )

        mock_templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["active_section"] == "roles"
        assert context["role"]["name"] == "editor"
        assert len(context["role"]["users"]) == 1

    async def test_detail_invalid_uuid(self, db):
        from auth.api.routes.admin.roles_pages import role_detail_page

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await role_detail_page(
                request=request,
                role_id="bad-uuid",
                db=db,
                auth=auth,
            )
        assert exc_info.value.status_code == 400

    async def test_detail_not_found(self, db):
        from auth.api.routes.admin.roles_pages import role_detail_page

        role_id = uuid.uuid4()
        role_result = make_execute_result(scalar_value=None)
        db.execute = AsyncMock(return_value=role_result)

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await role_detail_page(
                request=request,
                role_id=str(role_id),
                db=db,
                auth=auth,
            )
        assert exc_info.value.status_code == 404

    async def test_detail_no_users(self, db):
        from auth.api.routes.admin.roles_pages import role_detail_page

        role_id = uuid.uuid4()
        role = _make_role(role_id=role_id, name="empty_role")

        role_result = make_execute_result(scalar_value=role)
        users_result = MagicMock()
        users_result.all.return_value = []

        scope = _make_scope()
        scopes_result = make_execute_result(scalars_list=[scope])

        db.execute = AsyncMock(side_effect=[role_result, users_result, scopes_result])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_detail_page(
                request=request,
                role_id=str(role_id),
                db=db,
                auth=auth,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["role"]["users"] == []

    async def test_detail_with_user_no_email(self, db):
        from auth.api.routes.admin.roles_pages import role_detail_page

        role_id = uuid.uuid4()
        role = _make_role(role_id=role_id, name="viewer")

        role_result = make_execute_result(scalar_value=role)

        user = MagicMock()
        user.id = uuid.uuid4()
        user.is_active = True
        user_role = _make_user_role(user_id=user.id, role_id=role_id)

        users_result = MagicMock()
        users_result.all.return_value = [(user_role, user, None)]

        scopes_result = make_execute_result(scalars_list=[])

        db.execute = AsyncMock(side_effect=[role_result, users_result, scopes_result])

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_detail_page(
                request=request,
                role_id=str(role_id),
                db=db,
                auth=auth,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["role"]["users"][0]["email"] is None


# ===========================================================================
# ROLES PAGES: role_assign_page TESTS
# ===========================================================================


class TestRoleAssignPage:
    """Tests for role_assign_page."""

    async def test_assign_page_no_search(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_page

        role_id = uuid.uuid4()
        role = _make_role(role_id=role_id, name="editor")

        role_result = make_execute_result(scalar_value=role)
        db.execute = AsyncMock(return_value=role_result)

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_assign_page(
                request=request,
                role_id=str(role_id),
                db=db,
                auth=auth,
                page=1,
                search=None,
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["users"] == []
        assert context["search"] == ""

    async def test_assign_page_with_search(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_page

        role_id = uuid.uuid4()
        role = _make_role(role_id=role_id, name="editor")

        user = MagicMock()
        user.id = uuid.uuid4()
        user.is_active = True
        user.created_at = datetime.now(UTC)
        user_email = MagicMock()
        user_email.email = "found@example.com"

        role_result = make_execute_result(scalar_value=role)

        # Count query
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Users query
        users_query_result = MagicMock()
        users_query_result.all.return_value = [(user, user_email)]

        # Has role check
        has_role_result = make_execute_result(scalar_value=None)

        # User's current roles
        user_roles_result = make_execute_result(scalars_list=[])

        db.execute = AsyncMock(
            side_effect=[
                role_result,
                count_result,
                users_query_result,
                has_role_result,
                user_roles_result,
            ]
        )

        request = _make_request()
        auth = _make_auth()
        mock_templates = _make_templates_mock()

        with (
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=mock_templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_assign_page(
                request=request,
                role_id=str(role_id),
                db=db,
                auth=auth,
                page=1,
                search="found",
            )

        call_kwargs = mock_templates.TemplateResponse.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["search"] == "found"
        assert len(context["users"]) == 1
        assert context["users"][0]["email"] == "found@example.com"
        assert context["users"][0]["has_role"] is False

    async def test_assign_page_invalid_uuid(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_page

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await role_assign_page(
                request=request,
                role_id="bad",
                db=db,
                auth=auth,
                page=1,
                search=None,
            )
        assert exc_info.value.status_code == 400

    async def test_assign_page_role_not_found(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_page

        role_id = uuid.uuid4()
        role_result = make_execute_result(scalar_value=None)
        db.execute = AsyncMock(return_value=role_result)

        request = _make_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await role_assign_page(
                request=request,
                role_id=str(role_id),
                db=db,
                auth=auth,
                page=1,
                search=None,
            )
        assert exc_info.value.status_code == 404


# ===========================================================================
# ROLES PAGES: role_assign_submit TESTS
# ===========================================================================


class TestRoleAssignSubmit:
    """Tests for role_assign_submit."""

    async def test_assign_success(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_submit

        role_id = uuid.uuid4()
        user_id = uuid.uuid4()
        role = _make_role(role_id=role_id, name="editor")
        user = MagicMock()
        user.id = user_id

        role_result = make_execute_result(scalar_value=role)
        user_result = make_execute_result(scalar_value=user)
        existing_result = make_execute_result(scalar_value=None)

        db.execute = AsyncMock(side_effect=[role_result, user_result, existing_result])
        db.commit = AsyncMock()

        auth = _make_auth()

        result = await role_assign_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
            user_id=str(user_id),
            expires_at=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=User+assigned" in result.headers.get("location", "")

    async def test_assign_with_expiration(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_submit

        role_id = uuid.uuid4()
        user_id = uuid.uuid4()
        role = _make_role(role_id=role_id, name="editor")
        user = MagicMock()
        user.id = user_id

        role_result = make_execute_result(scalar_value=role)
        user_result = make_execute_result(scalar_value=user)
        existing_result = make_execute_result(scalar_value=None)

        db.execute = AsyncMock(side_effect=[role_result, user_result, existing_result])
        db.commit = AsyncMock()

        auth = _make_auth()

        result = await role_assign_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
            user_id=str(user_id),
            expires_at="2030-12-31T00:00:00",
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers.get("location", "")

    async def test_assign_invalid_ids(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_submit

        auth = _make_auth()

        result = await role_assign_submit(
            role_id="bad",
            db=db,
            auth=auth,
            user_id="also-bad",
            expires_at=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+ID" in result.headers.get("location", "")

    async def test_assign_role_not_found(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_submit

        role_id = uuid.uuid4()
        user_id = uuid.uuid4()

        role_result = make_execute_result(scalar_value=None)
        db.execute = AsyncMock(return_value=role_result)

        auth = _make_auth()

        result = await role_assign_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
            user_id=str(user_id),
            expires_at=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Role+not+found" in result.headers.get("location", "")

    async def test_assign_user_not_found(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_submit

        role_id = uuid.uuid4()
        user_id = uuid.uuid4()
        role = _make_role(role_id=role_id)

        role_result = make_execute_result(scalar_value=role)
        user_result = make_execute_result(scalar_value=None)

        db.execute = AsyncMock(side_effect=[role_result, user_result])

        auth = _make_auth()

        result = await role_assign_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
            user_id=str(user_id),
            expires_at=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+not+found" in result.headers.get("location", "")

    async def test_assign_already_has_role(self, db):
        from auth.api.routes.admin.roles_pages import role_assign_submit

        role_id = uuid.uuid4()
        user_id = uuid.uuid4()
        role = _make_role(role_id=role_id)
        user = MagicMock()
        user.id = user_id

        existing_ur = _make_user_role(user_id=user_id, role_id=role_id)

        role_result = make_execute_result(scalar_value=role)
        user_result = make_execute_result(scalar_value=user)
        existing_result = make_execute_result(scalar_value=existing_ur)

        db.execute = AsyncMock(side_effect=[role_result, user_result, existing_result])

        auth = _make_auth()

        result = await role_assign_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
            user_id=str(user_id),
            expires_at=None,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=User+already+has" in result.headers.get("location", "")


# ===========================================================================
# ROLES PAGES: role_remove_user_submit TESTS
# ===========================================================================


class TestRoleRemoveUserSubmit:
    """Tests for role_remove_user_submit."""

    async def test_remove_success(self, db):
        from auth.api.routes.admin.roles_pages import role_remove_user_submit

        role_id = uuid.uuid4()
        user_id = uuid.uuid4()

        ur = _make_user_role(user_id=user_id, role_id=role_id)
        ur_result = make_execute_result(scalar_value=ur)
        db.execute = AsyncMock(return_value=ur_result)
        db.delete = AsyncMock()
        db.commit = AsyncMock()

        auth = _make_auth()

        result = await role_remove_user_submit(
            role_id=str(role_id),
            user_id=str(user_id),
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=User+removed" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(ur)

    async def test_remove_invalid_ids(self, db):
        from auth.api.routes.admin.roles_pages import role_remove_user_submit

        auth = _make_auth()

        result = await role_remove_user_submit(
            role_id="bad",
            user_id="bad",
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+ID" in result.headers.get("location", "")

    async def test_remove_not_found(self, db):
        from auth.api.routes.admin.roles_pages import role_remove_user_submit

        role_id = uuid.uuid4()
        user_id = uuid.uuid4()

        ur_result = make_execute_result(scalar_value=None)
        db.execute = AsyncMock(return_value=ur_result)

        auth = _make_auth()

        result = await role_remove_user_submit(
            role_id=str(role_id),
            user_id=str(user_id),
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Role+assignment+not+found" in result.headers.get("location", "")


# ===========================================================================
# ROLES PAGES: role_delete_submit TESTS
# ===========================================================================


class TestRoleDeleteSubmit:
    """Tests for role_delete_submit."""

    async def test_delete_success(self, db):
        from auth.api.routes.admin.roles_pages import role_delete_submit

        role_id = uuid.uuid4()
        role = _make_role(role_id=role_id, is_system=False)

        role_result = make_execute_result(scalar_value=role)
        db.execute = AsyncMock(return_value=role_result)
        db.delete = AsyncMock()
        db.commit = AsyncMock()

        auth = _make_auth()

        result = await role_delete_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=Role+deleted" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(role)

    async def test_delete_system_role_forbidden(self, db):
        from auth.api.routes.admin.roles_pages import role_delete_submit

        role_id = uuid.uuid4()
        role = _make_role(role_id=role_id, is_system=True)

        role_result = make_execute_result(scalar_value=role)
        db.execute = AsyncMock(return_value=role_result)

        auth = _make_auth()

        result = await role_delete_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Cannot+delete+system" in result.headers.get("location", "")

    async def test_delete_invalid_uuid(self, db):
        from auth.api.routes.admin.roles_pages import role_delete_submit

        auth = _make_auth()

        result = await role_delete_submit(
            role_id="bad",
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Invalid+role+ID" in result.headers.get("location", "")

    async def test_delete_not_found(self, db):
        from auth.api.routes.admin.roles_pages import role_delete_submit

        role_id = uuid.uuid4()
        role_result = make_execute_result(scalar_value=None)
        db.execute = AsyncMock(return_value=role_result)

        auth = _make_auth()

        result = await role_delete_submit(
            role_id=str(role_id),
            db=db,
            auth=auth,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error=Role+not+found" in result.headers.get("location", "")


# ===========================================================================
# ROLES PAGES: seed_default_roles_submit TESTS
# ===========================================================================


class TestSeedDefaultRolesSubmit:
    """Tests for seed_default_roles_submit."""

    @patch(
        f"{ROLES_PAGES_MODULE}.DEFAULT_ROLES",
        {
            "test_admin": {
                "description": "Test admin role",
                "scopes": ["users:read"],
                "is_system": True,
            },
        },
    )
    async def test_seed_creates_new_roles(self, db):
        from auth.api.routes.admin.roles_pages import seed_default_roles_submit

        scope = _make_scope(name="users:read")

        # 1: fetch all scopes
        scopes_result = make_execute_result(scalars_list=[scope])
        # 2: check existing role "test_admin" => None
        existing_result = make_execute_result(scalar_value=None)

        db.execute = AsyncMock(side_effect=[scopes_result, existing_result])
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        auth = _make_auth()
        result = await seed_default_roles_submit(db=db, auth=auth)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=" in result.headers.get("location", "")

    @patch(
        f"{ROLES_PAGES_MODULE}.DEFAULT_ROLES",
        {
            "existing_role": {
                "description": "Already exists",
                "scopes": [],
                "is_system": True,
            },
        },
    )
    async def test_seed_skips_existing_roles(self, db):
        from auth.api.routes.admin.roles_pages import seed_default_roles_submit

        existing_role = _make_role(name="existing_role")

        scopes_result = make_execute_result(scalars_list=[])
        existing_result = make_execute_result(scalar_value=existing_role)

        db.execute = AsyncMock(side_effect=[scopes_result, existing_result])
        db.commit = AsyncMock()

        auth = _make_auth()
        result = await seed_default_roles_submit(db=db, auth=auth)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success=All+default+roles+already+exist" in result.headers.get("location", "")


# ===========================================================================
# Remaining branches
# ===========================================================================


class TestRolePagesScopeGrouping:
    """Two scopes in one category exercise the "category already present" arm."""

    async def test_create_page_groups_by_category(self, db):
        from auth.api.routes.admin.roles_pages import role_create_page

        scopes = [
            _make_scope(name="users:read", category="admin"),
            _make_scope(name="users:write", category="admin"),
        ]
        templates = _make_templates_mock()

        with (
            patch(
                f"{ROLES_PAGES_MODULE}._scope_service.list_active",
                AsyncMock(return_value=scopes),
            ),
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_create_page(request=_make_request(), db=db, auth=_make_auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert len(ctx["scopes_by_category"]["admin"]) == 2

    async def test_detail_page_groups_by_category(self, db):
        from auth.api.routes.admin.roles_pages import role_detail_page

        role = _make_role()
        scopes = [
            _make_scope(name="users:read", category="admin"),
            _make_scope(name="users:write", category="admin"),
        ]
        templates = _make_templates_mock()

        with (
            patch(
                f"{ROLES_PAGES_MODULE}._role_service.get_by_id",
                AsyncMock(return_value=role),
            ),
            patch(
                f"{ROLES_PAGES_MODULE}._role_service.list_users_for_role",
                AsyncMock(return_value=[]),
            ),
            patch(
                f"{ROLES_PAGES_MODULE}._scope_service.list_active",
                AsyncMock(return_value=scopes),
            ),
            patch(f"{ROLES_PAGES_MODULE}.get_templates", return_value=templates),
            patch(
                f"{ROLES_PAGES_MODULE}.get_user_admin_permissions",
                return_value=_mock_permissions(),
            ),
        ):
            await role_detail_page(
                request=_make_request(), role_id=str(role.id), db=db, auth=_make_auth()
            )

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert len(ctx["scopes_by_category"]["admin"]) == 2


class TestRoleCreateSubmitBranches:
    async def test_duplicate_scopes_are_collapsed(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        role = _make_role()

        with patch(
            f"{ROLES_PAGES_MODULE}._role_service.create_role_by_scope_names",
            AsyncMock(return_value=role),
        ) as create:
            await role_create_submit(
                request=_make_request(),
                db=db,
                auth=_make_auth(),
                name="editor",
                description=None,
                scopes=["users:read", "users:read"],
                wildcard_scopes="users:read, users:write",
            )

        assert create.await_args.kwargs["scope_names"] == ["users:read", "users:write"]

    async def test_other_value_error_is_surfaced_verbatim(self, db):
        from auth.api.routes.admin.roles_pages import role_create_submit

        with patch(
            f"{ROLES_PAGES_MODULE}._role_service.create_role_by_scope_names",
            AsyncMock(side_effect=ValueError("Name must not be blank")),
        ):
            result = await role_create_submit(
                request=_make_request(),
                db=db,
                auth=_make_auth(),
                name="",
                description=None,
                scopes=None,
                wildcard_scopes=None,
            )

        assert result.status_code == 303
        assert "error=Name%20must%20not%20be%20blank" in result.headers["location"]


class TestSeedDefaultRolesUnknownScope:
    async def test_scopes_missing_from_the_catalogue_are_skipped(self, db):
        from auth.api.routes.admin.roles_pages import _seed_default_roles
        from auth.db.models.rbac import DEFAULT_ROLES

        with (
            patch(f"{ROLES_PAGES_MODULE}._scope_service.list_active", AsyncMock(return_value=[])),
            patch(f"{ROLES_PAGES_MODULE}._role_service.get_by_name", AsyncMock(return_value=None)),
            patch(f"{ROLES_PAGES_MODULE}._role_service.add_role", AsyncMock()),
            patch(f"{ROLES_PAGES_MODULE}._role_service.add_role_scope", AsyncMock()) as add_scope,
        ):
            created = await _seed_default_roles(db)

        assert created == list(DEFAULT_ROLES)
        add_scope.assert_not_awaited()


class TestUserEditSubmitEmailLoop:
    async def test_user_without_a_primary_email_is_still_saved(self, db):
        from auth.api.routes.admin.users_pages import user_edit_submit

        user = _make_user_with_emails_and_profile()
        for email in user.emails:
            email.is_primary = False

        user_service = _patch_user_service(user=user)

        with patch(f"{USERS_PAGES_MODULE}._user_service", user_service):
            result = await user_edit_submit(
                request=_make_request(),
                user_id=str(user.id),
                db=db,
                profile_service=AsyncMock(),
                auth=_make_auth(),
                is_active="true",
                is_verified="true",
            )

        assert result.status_code == 303
        db.commit.assert_awaited()
