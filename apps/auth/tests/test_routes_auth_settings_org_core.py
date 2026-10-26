# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the organisation-membership handlers of auth.api.routes.auth.settings.

Covers leaving a tenant, unlinking a federated identity, slug generation and
organisation creation.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MODULE = "auth.api.routes.auth.settings"


def _request(cookies=None):
    request = MagicMock()
    request.cookies = cookies if cookies is not None else {"session": "tok"}
    request.query_params = {}
    request.headers = {}
    url = MagicMock()
    url.scheme = "https"
    url.netloc = "auth.example.com"
    url.path = "/auth/settings/organisations"
    url.query = ""
    request.url = url
    request.base_url = "https://auth.example.com/"
    return request


def _user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _session_service(user):
    service = AsyncMock()
    service.get_user_by_session_token = AsyncMock(return_value=user)
    return service


def _membership(scopes=("members:read",)):
    membership = MagicMock()
    membership.id = uuid.uuid4()
    membership.has_scope = lambda scope: scope in scopes
    return membership


# ---------------------------------------------------------------------------
# settings_leave_tenant
# ---------------------------------------------------------------------------


class TestLeaveTenant:
    async def test_no_cookie_redirects_to_login(self):
        from auth.api.routes.auth.settings import settings_leave_tenant

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_leave_tenant(
                _request(cookies={}), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "/auth/login" in result.headers["location"]

    async def test_unparseable_tenant_id_is_reported(self):
        from auth.api.routes.auth.settings import settings_leave_tenant

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_leave_tenant(
                _request(), "not-a-uuid", AsyncMock(), _session_service(_user())
            )

        assert "error=Invalid+tenant+ID" in result.headers["location"]

    async def test_non_member_is_reported(self):
        from auth.api.routes.auth.settings import settings_leave_tenant

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.tenant_service.get_member", AsyncMock(return_value=None)),
        ):
            result = await settings_leave_tenant(
                _request(), str(uuid.uuid4()), AsyncMock(), _session_service(_user())
            )

        assert "error=You+are+not+a+member" in result.headers["location"]

    async def test_sole_owner_cannot_leave(self):
        from auth.api.routes.auth.settings import settings_leave_tenant

        owner = _membership(scopes=("*",))

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.tenant_service.get_member", AsyncMock(return_value=owner)),
            patch(f"{MODULE}.tenant_service.list_members", AsyncMock(return_value=[owner])),
        ):
            result = await settings_leave_tenant(
                _request(), str(uuid.uuid4()), AsyncMock(), _session_service(_user())
            )

        assert "error=Cannot+leave" in result.headers["location"]

    async def test_owner_with_a_co_owner_may_leave(self):
        from auth.api.routes.auth.settings import settings_leave_tenant

        owner, co_owner = _membership(scopes=("*",)), _membership(scopes=("*",))
        db = AsyncMock()

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.tenant_service.get_member", AsyncMock(return_value=owner)),
            patch(
                f"{MODULE}.tenant_service.list_members",
                AsyncMock(return_value=[owner, co_owner]),
            ),
            patch(f"{MODULE}.tenant_service.remove_member", AsyncMock()) as remove,
            patch(
                f"{MODULE}.federation_service.list_federated_identities_for_user_in_tenant",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await settings_leave_tenant(
                _request(), str(uuid.uuid4()), db, _session_service(_user())
            )

        remove.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert "success=You+have+left" in result.headers["location"]

    async def test_federated_identities_are_unlinked(self):
        from auth.api.routes.auth.settings import settings_leave_tenant

        fed = MagicMock()

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.tenant_service.get_member", AsyncMock(return_value=_membership())),
            patch(f"{MODULE}.tenant_service.remove_member", AsyncMock()),
            patch(
                f"{MODULE}.federation_service.list_federated_identities_for_user_in_tenant",
                AsyncMock(return_value=[fed]),
            ),
            patch(f"{MODULE}.federation_service.delete_federated_identity", AsyncMock()) as delete,
        ):
            await settings_leave_tenant(
                _request(), str(uuid.uuid4()), AsyncMock(), _session_service(_user())
            )

        delete.assert_awaited_once()
        assert delete.await_args[0][1] is fed


# ---------------------------------------------------------------------------
# settings_unlink_tenant_idp
# ---------------------------------------------------------------------------


class TestUnlinkTenantIdp:
    async def test_no_cookie_redirects_to_login(self):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_unlink_tenant_idp(
                _request(cookies={}),
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "/auth/login" in result.headers["location"]

    async def test_stale_session_redirects_to_login(self):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_unlink_tenant_idp(
                _request(),
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                AsyncMock(),
                _session_service(None),
            )

        assert "/auth/login" in result.headers["location"]

    async def test_unparseable_idp_id_is_reported(self):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_unlink_tenant_idp(
                _request(),
                str(uuid.uuid4()),
                "not-a-uuid",
                AsyncMock(),
                _session_service(_user()),
            )

        assert "error=Invalid+IdP+ID" in result.headers["location"]

    async def test_missing_link_is_reported(self):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.federation_service.get_federated_identity",
                AsyncMock(return_value=None),
            ),
        ):
            result = await settings_unlink_tenant_idp(
                _request(),
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                AsyncMock(),
                _session_service(_user()),
            )

        assert "error=Identity+provider+link+not+found" in result.headers["location"]

    async def test_link_is_removed(self):
        from auth.api.routes.auth.settings import settings_unlink_tenant_idp

        db = AsyncMock()

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.federation_service.get_federated_identity",
                AsyncMock(return_value=MagicMock()),
            ),
            patch(f"{MODULE}.federation_service.delete_federated_identity", AsyncMock()) as delete,
        ):
            result = await settings_unlink_tenant_idp(
                _request(),
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                db,
                _session_service(_user()),
            )

        delete.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert "success=Identity+provider+unlinked" in result.headers["location"]


# ---------------------------------------------------------------------------
# generate_tenant_slug
# ---------------------------------------------------------------------------


class TestGenerateTenantSlug:
    def test_spaces_and_punctuation_become_hyphens(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        assert generate_tenant_slug("Acme Corp!") == "acme-corp"

    def test_leading_and_trailing_hyphens_are_stripped(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        assert generate_tenant_slug("  --Acme--  ") == "acme"

    def test_long_names_are_truncated(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        assert len(generate_tenant_slug("a" * 200)) == 50

    def test_unsluggable_name_falls_back(self):
        from auth.api.routes.auth.settings import generate_tenant_slug

        assert generate_tenant_slug("!!!") == "org"


# ---------------------------------------------------------------------------
# settings_create_tenant
# ---------------------------------------------------------------------------


def _auth(user=None):
    return (user or _user(), [MagicMock()])


def _owner_role():
    role = MagicMock()
    role.name = "owner"
    role.id = uuid.uuid4()
    return role


class TestCreateTenant:
    async def test_blank_name_is_rejected(self):
        from auth.api.routes.auth.settings import settings_create_tenant

        result = await settings_create_tenant(_request(), AsyncMock(), _auth(), "   ")

        assert "error=Organization+name+is+required" in result.headers["location"]

    async def test_overlong_name_is_rejected(self):
        from auth.api.routes.auth.settings import settings_create_tenant

        result = await settings_create_tenant(_request(), AsyncMock(), _auth(), "a" * 256)

        assert "less+than+256" in result.headers["location"]

    async def test_slug_collision_is_retried_then_given_up_on(self):
        from auth.api.routes.auth.settings import settings_create_tenant

        with patch(f"{MODULE}.tenant_service.slug_exists", AsyncMock(return_value=True)):
            result = await settings_create_tenant(_request(), AsyncMock(), _auth(), "Acme Corp")

        assert "error=Failed+to+create+organization" in result.headers["location"]

    async def test_first_membership_leaves_scopes_unrestricted(self):
        from auth.api.routes.auth.settings import settings_create_tenant

        staged = {}

        async def _add_tenant(_db, tenant):
            staged["tenant"] = tenant
            tenant.id = uuid.uuid4()

        with (
            patch(f"{MODULE}.tenant_service.slug_exists", AsyncMock(return_value=False)),
            patch(
                f"{MODULE}.tenant_service.list_user_memberships_with_custom_role",
                AsyncMock(return_value=[]),
            ),
            patch(f"{MODULE}.tenant_service.add_tenant", AsyncMock(side_effect=_add_tenant)),
            patch(
                f"{MODULE}.tenant_role_service.create_default_roles",
                AsyncMock(return_value=[_owner_role()]),
            ),
            patch(f"{MODULE}.tenant_service.add_member", AsyncMock()) as add_member,
        ):
            result = await settings_create_tenant(_request(), AsyncMock(), _auth(), "Acme Corp")

        assert staged["tenant"].slug == "acme-corp"
        assert staged["tenant"].settings is None
        add_member.assert_awaited_once()
        assert "created+successfully" in result.headers["location"]

    async def test_wildcard_scope_leaves_the_new_org_unrestricted(self):
        from auth.api.routes.auth.settings import settings_create_tenant

        membership = MagicMock()
        membership.custom_role = MagicMock()
        membership.custom_role.scopes = ["*"]
        staged = {}

        async def _add_tenant(_db, tenant):
            staged["tenant"] = tenant
            tenant.id = uuid.uuid4()

        with (
            patch(f"{MODULE}.tenant_service.slug_exists", AsyncMock(return_value=False)),
            patch(
                f"{MODULE}.tenant_service.list_user_memberships_with_custom_role",
                AsyncMock(return_value=[membership]),
            ),
            patch(f"{MODULE}.tenant_service.add_tenant", AsyncMock(side_effect=_add_tenant)),
            patch(
                f"{MODULE}.tenant_role_service.create_default_roles",
                AsyncMock(return_value=[_owner_role()]),
            ),
            patch(f"{MODULE}.tenant_service.add_member", AsyncMock()),
        ):
            await settings_create_tenant(_request(), AsyncMock(), _auth(), "Acme Corp")

        assert staged["tenant"].settings is None

    async def test_restricted_scopes_are_inherited_and_expanded(self):
        from auth.api.routes.auth.settings import TENANT_SCOPES, settings_create_tenant

        exact = next(s for s in TENANT_SCOPES if ":" in s)
        resource = exact.split(":")[0]

        membership = MagicMock()
        membership.custom_role = MagicMock()
        membership.custom_role.scopes = [exact, f"{resource}:*", "unknown:scope"]
        role_without_custom = MagicMock()
        role_without_custom.custom_role = None
        staged = {}

        async def _add_tenant(_db, tenant):
            staged["tenant"] = tenant
            tenant.id = uuid.uuid4()

        with (
            patch(f"{MODULE}.tenant_service.slug_exists", AsyncMock(return_value=False)),
            patch(
                f"{MODULE}.tenant_service.list_user_memberships_with_custom_role",
                AsyncMock(return_value=[membership, role_without_custom]),
            ),
            patch(f"{MODULE}.tenant_service.add_tenant", AsyncMock(side_effect=_add_tenant)),
            patch(
                f"{MODULE}.tenant_role_service.create_default_roles",
                AsyncMock(return_value=[_owner_role()]),
            ),
            patch(f"{MODULE}.tenant_service.add_member", AsyncMock()),
        ):
            await settings_create_tenant(_request(), AsyncMock(), _auth(), "Acme Corp")

        allowed = staged["tenant"].settings["allowed_scopes"]
        assert exact in allowed
        assert f"{resource}:*" in allowed
        assert "unknown:scope" not in allowed

    async def test_scopes_that_resolve_to_nothing_leave_the_org_unrestricted(self):
        from auth.api.routes.auth.settings import settings_create_tenant

        membership = MagicMock()
        membership.custom_role = MagicMock()
        membership.custom_role.scopes = ["unknown:scope"]
        staged = {}

        async def _add_tenant(_db, tenant):
            staged["tenant"] = tenant
            tenant.id = uuid.uuid4()

        with (
            patch(f"{MODULE}.tenant_service.slug_exists", AsyncMock(return_value=False)),
            patch(
                f"{MODULE}.tenant_service.list_user_memberships_with_custom_role",
                AsyncMock(return_value=[membership]),
            ),
            patch(f"{MODULE}.tenant_service.add_tenant", AsyncMock(side_effect=_add_tenant)),
            patch(
                f"{MODULE}.tenant_role_service.create_default_roles",
                AsyncMock(return_value=[_owner_role()]),
            ),
            patch(f"{MODULE}.tenant_service.add_member", AsyncMock()),
        ):
            await settings_create_tenant(_request(), AsyncMock(), _auth(), "Acme Corp")

        assert staged["tenant"].settings is None

    async def test_missing_owner_role_is_a_500(self):
        from auth.api.routes.auth.settings import settings_create_tenant
        from fastapi import HTTPException

        other = MagicMock()
        other.name = "member"

        with (
            patch(f"{MODULE}.tenant_service.slug_exists", AsyncMock(return_value=False)),
            patch(
                f"{MODULE}.tenant_service.list_user_memberships_with_custom_role",
                AsyncMock(return_value=[]),
            ),
            patch(f"{MODULE}.tenant_service.add_tenant", AsyncMock()),
            patch(
                f"{MODULE}.tenant_role_service.create_default_roles",
                AsyncMock(return_value=[other]),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await settings_create_tenant(_request(), AsyncMock(), _auth(), "Acme Corp")

        assert exc.value.status_code == 500


class TestCreateTenantWildcardScopeExpansion:
    async def test_a_wildcard_scope_is_expanded_and_kept(self):
        from auth.api.routes.auth.settings import TENANT_SCOPES, settings_create_tenant

        # A resource wildcard whose siblings are not in the catalogue still
        # survives verbatim so the new org inherits the grant.
        membership = MagicMock()
        membership.custom_role = MagicMock()
        membership.custom_role.scopes = ["unknown:*"]
        staged = {}

        async def _add_tenant(_db, tenant):
            staged["tenant"] = tenant
            tenant.id = uuid.uuid4()

        with (
            patch(f"{MODULE}.tenant_service.slug_exists", AsyncMock(return_value=False)),
            patch(
                f"{MODULE}.tenant_service.list_user_memberships_with_custom_role",
                AsyncMock(return_value=[membership]),
            ),
            patch(f"{MODULE}.tenant_service.add_tenant", AsyncMock(side_effect=_add_tenant)),
            patch(
                f"{MODULE}.tenant_role_service.create_default_roles",
                AsyncMock(return_value=[_owner_role()]),
            ),
            patch(f"{MODULE}.tenant_service.add_member", AsyncMock()),
        ):
            await settings_create_tenant(_request(), AsyncMock(), _auth(), "Acme Corp")

        allowed = staged["tenant"].settings["allowed_scopes"]
        assert allowed == ["unknown:*"]
        assert "unknown:*" not in TENANT_SCOPES
