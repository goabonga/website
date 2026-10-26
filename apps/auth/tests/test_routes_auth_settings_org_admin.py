# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the /auth/settings/org/* handlers of auth.api.routes.auth.settings.

These handlers all authorise through ``require_tenant_manager``; the tests patch
that helper and drive each handler directly.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MODULE = "auth.api.routes.auth.settings"


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(UTC)


def _request(query_params=None, form_data=None):
    request = MagicMock()
    request.cookies = {"session": "tok"}
    request.query_params = query_params or {}
    request.headers = {}
    url = MagicMock()
    url.scheme = "https"
    url.netloc = "auth.example.com"
    url.path = "/auth/settings/org"
    url.query = ""
    request.url = url
    request.base_url = "https://auth.example.com/"
    data = form_data or {}
    form = MagicMock()
    form.get = lambda key, default="": data.get(key, default)
    form.items = lambda: data.items()
    form.getlist = lambda key: data.get(key, [])
    # Handlers scan the raw keys for ``scope_``/``grant_`` checkboxes.
    form.__iter__ = lambda _self: iter(data)
    request.form = AsyncMock(return_value=form)
    return request


def _user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _role(name="member", scopes=("members:read",), tenant_id=None, is_system=False):
    role = MagicMock()
    role.id = uuid.uuid4()
    role.name = name
    role.display_name = name.capitalize()
    role.description = None
    role.scopes = list(scopes)
    role.is_system = is_system
    role.is_default = False
    role.tenant_id = tenant_id or uuid.uuid4()
    role.has_scope = lambda s: s in scopes or "*" in scopes
    return role


def _member(tenant_id=None, scopes=("members:read",), role_id=None):
    member = MagicMock()
    member.id = uuid.uuid4()
    member.user_id = uuid.uuid4()
    member.tenant_id = tenant_id or uuid.uuid4()
    member.role_id = role_id or uuid.uuid4()
    member.role_name = "member"
    member.role_display_name = "Member"
    member.role_scopes = list(scopes)
    member.joined_at = _now()
    member.invited_at = None
    member.invited_by = None
    member.created_at = _now()
    member.has_scope = lambda s: s in scopes or "*" in scopes
    member.user = MagicMock()
    member.user.profile = MagicMock()
    member.user.profile.name = "Test User"
    member.custom_role = MagicMock()
    member.custom_role.name = "member"
    return member


def _tenant(settings=None, members=None, idps=None, roles=None, branding=None, templates=None):
    tenant = MagicMock()
    tenant.id = uuid.uuid4()
    tenant.slug = "acme"
    tenant.display_name = "Acme Corp"
    tenant.custom_domain = None
    tenant.custom_domain_status = None
    tenant.custom_domain_verified_at = None
    tenant.custom_domain_ssl_at = None
    tenant.custom_domain_error = None
    tenant.custom_domain_checked_at = None
    tenant.is_active = True
    tenant.settings = settings if settings is not None else {}
    tenant.members = members or []
    tenant.identity_providers = idps or []
    tenant.roles = roles or []
    tenant.branding = branding
    tenant.templates = templates or []
    tenant.created_at = _now()
    tenant.updated_at = _now()
    return tenant


def _authorised(tenant=None, membership=None, user=None):
    """Patch the authorisation helper to return a ready-made (user, tenant, membership).

    Handlers call the module-level ``require_tenant_manager``, which is bound at
    import time, so that name is what has to be patched. The scope each handler
    passes to it is checked by ``test_routes_auth_settings_org_scopes.py``.
    """
    tenant = tenant or _tenant()
    membership = membership if membership is not None else _member(tenant.id, scopes=("*",))
    return patch(
        f"{MODULE}.require_tenant_manager",
        AsyncMock(return_value=(user or _user(), tenant, membership)),
    )


def _patch_page(templates=None):
    """Patch the page-rendering side dependencies shared by every org GET page."""
    templates = templates or MagicMock()
    templates.TemplateResponse.return_value = MagicMock()
    return templates, (
        patch(f"{MODULE}.get_templates", return_value=templates),
        patch(f"{MODULE}.check_user_is_admin", AsyncMock(return_value=(False, {}))),
        patch(f"{MODULE}.get_branding_for_request", AsyncMock(return_value="branding")),
        patch(f"{MODULE}.get_tenant_prefix", return_value=""),
    )


def _enter(patches):
    """Enter a tuple of context managers and return a closer."""
    entered = [p.__enter__() for p in patches]
    return entered, lambda: [p.__exit__(None, None, None) for p in reversed(patches)]


def _scope(name="members:read"):
    scope = MagicMock()
    scope.id = uuid.uuid4()
    scope.name = name
    scope.description = "desc"
    scope.category = "org"
    scope.resource = name.split(":")[0]
    scope.action = name.split(":")[-1]
    return scope


# ---------------------------------------------------------------------------
# org_detail_page
# ---------------------------------------------------------------------------


class TestOrgDetailPage:
    async def test_renders_members_idps_and_webhooks(self):
        from auth.api.routes.auth.settings import org_detail_page

        role = _role()
        tenant = _tenant(members=[_member()], idps=[], roles=[role])
        membership = _member(tenant.id, scopes=("*",))
        templates, page_patches = _patch_page()

        trust_service = AsyncMock()
        trust_service.get_tenant_trust_config = AsyncMock(
            return_value={"trust_mode": "none", "trusted_sources": []}
        )
        trust_service.get_available_tenants_for_trust = AsyncMock(return_value=[])

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant, membership),
                patch(
                    f"{MODULE}.tenant_service.get_member_primary_email",
                    AsyncMock(return_value="m@example.com"),
                ),
                patch(f"{MODULE}._load_tenant_webhooks", AsyncMock(return_value=[{"id": "w"}])),
            )
        )
        try:
            await org_detail_page(
                _request(), str(tenant.id), AsyncMock(), AsyncMock(), trust_service
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["members"][0]["user_email"] == "m@example.com"
        assert ctx["can"]["webhooks:read"] is True
        assert ctx["webhooks"] == [{"id": "w"}]
        assert ctx["trust_mode"] == "none"

    async def test_member_without_webhook_scope_sees_none(self):
        from auth.api.routes.auth.settings import org_detail_page

        tenant = _tenant()
        membership = _member(tenant.id, scopes=("settings:read",))
        templates, page_patches = _patch_page()

        trust_service = AsyncMock()
        trust_service.get_tenant_trust_config = AsyncMock(return_value=None)
        trust_service.get_available_tenants_for_trust = AsyncMock(return_value=[])

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant, membership),
                patch(f"{MODULE}._load_tenant_webhooks", AsyncMock()),
            )
        )
        try:
            await org_detail_page(
                _request(), str(tenant.id), AsyncMock(), AsyncMock(), trust_service
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["can"]["webhooks:read"] is False
        assert ctx["can"]["idp:write"] is False
        assert ctx["webhooks"] == []
        assert ctx["trust_mode"] == "none"
        assert ctx["trusted_sources"] == []


# ---------------------------------------------------------------------------
# org_edit_page
# ---------------------------------------------------------------------------


class TestOrgEditPage:
    async def test_allowed_scopes_are_intersected_with_the_users_scopes(self):
        from auth.api.routes.auth.settings import org_edit_page

        tenant = _tenant(settings={"allowed_scopes": ["members:read", "members:write"]})
        membership = _member(tenant.id, scopes=("members:read",))
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant, membership),
                patch(
                    f"{MODULE}.scope_service.list_active",
                    AsyncMock(return_value=[_scope("members:read"), _scope("members:write")]),
                ),
            )
        )
        try:
            await org_edit_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["current_allowed"] == {"members:read"}

    async def test_no_allowed_list_yields_an_empty_set(self):
        from auth.api.routes.auth.settings import org_edit_page

        tenant = _tenant()
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[])),
            )
        )
        try:
            await org_edit_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["current_allowed"] == set()

    async def test_the_page_receives_the_scopes_of_the_member(self):
        from auth.api.routes.auth.settings import OrgPermissions, org_edit_page

        tenant = _tenant()
        membership = _member(tenant.id, scopes=("settings:read", "domain:read", "domain:write"))
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant, membership),
                patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[])),
            )
        )
        try:
            await org_edit_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        can = templates.TemplateResponse.call_args.kwargs["context"]["can"]
        assert isinstance(can, OrgPermissions)
        assert can["domain:write"] is True
        assert can["domain:read"] is True
        assert can["settings:write"] is False

    @pytest.mark.parametrize(
        ("cname_target", "base_domain", "expected"),
        [
            ("edge.example.test", "auth.example.test", "edge.example.test"),
            ("", "auth.example.test", "auth.example.test"),
            ("", "", ""),
        ],
    )
    async def test_cname_target_falls_back_to_the_base_domain(
        self, cname_target, base_domain, expected
    ):
        from auth.api.routes.auth.settings import org_edit_page

        tenant = _tenant()
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[])),
                patch(f"{MODULE}.settings.custom_domain_cname_target", cname_target),
                patch(f"{MODULE}.settings.tenant_base_domain", base_domain),
            )
        )
        try:
            await org_edit_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["cname_target"] == expected


# ---------------------------------------------------------------------------
# org_edit_submit
# ---------------------------------------------------------------------------


class TestOrgEditSubmit:
    async def test_blank_display_name_is_rejected(self):
        from auth.api.routes.auth.settings import org_edit_submit

        tenant = _tenant()
        with _authorised(tenant):
            result = await org_edit_submit(
                _request(form_data={"display_name": "  "}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Display+name+is+required" in result.headers["location"]

    async def test_overlong_display_name_is_rejected(self):
        from auth.api.routes.auth.settings import org_edit_submit

        tenant = _tenant()
        with _authorised(tenant):
            result = await org_edit_submit(
                _request(form_data={"display_name": "a" * 256}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "less+than+256" in result.headers["location"]

    async def test_the_custom_domain_field_is_ignored(self):
        """The domain has its own route and scope: this form never changes it."""
        from auth.api.routes.auth.settings import org_edit_submit

        tenant = _tenant()
        tenant.custom_domain = "acme.example.com"
        module = MagicMock()

        with (
            _authorised(tenant),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
            patch.dict("sys.modules", {"auth.tasks.custom_domain": module}),
        ):
            result = await org_edit_submit(
                _request(form_data={"display_name": "Acme", "custom_domain": "evil.example.com"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.display_name == "Acme"
        assert tenant.custom_domain == "acme.example.com"
        module.verify_custom_domain_dns.delay.assert_not_called()
        module.remove_custom_domain_config.delay.assert_not_called()
        assert "success=Organization+updated" in result.headers["location"]


# ---------------------------------------------------------------------------
# org_domain_submit
# ---------------------------------------------------------------------------


class TestOrgDomainSubmit:
    async def test_new_custom_domain_starts_verification(self):
        from auth.api.routes.auth.settings import org_domain_submit
        from auth.db.models.tenant import CustomDomainStatus

        tenant = _tenant()
        verify = MagicMock()

        with (
            _authorised(tenant),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
            patch.dict(
                "sys.modules",
                {
                    "auth.tasks.custom_domain": MagicMock(
                        verify_custom_domain_dns=verify,
                        remove_custom_domain_config=MagicMock(),
                    )
                },
            ),
        ):
            result = await org_domain_submit(
                _request(form_data={"custom_domain": "acme.example.com"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.custom_domain_status is CustomDomainStatus.PENDING
        verify.delay.assert_called_once()
        assert "success=Custom+domain+updated" in result.headers["location"]

    async def test_removing_a_domain_triggers_config_cleanup(self):
        from auth.api.routes.auth.settings import org_domain_submit

        tenant = _tenant()
        tenant.custom_domain = "old.example.com"
        remove = MagicMock()

        with (
            _authorised(tenant),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
            patch.dict(
                "sys.modules",
                {
                    "auth.tasks.custom_domain": MagicMock(
                        verify_custom_domain_dns=MagicMock(),
                        remove_custom_domain_config=remove,
                    )
                },
            ),
        ):
            await org_domain_submit(
                _request(form_data={"custom_domain": ""}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.custom_domain is None
        assert tenant.custom_domain_status is None
        remove.delay.assert_called_once_with("old.example.com", "acme")

    async def test_unchanged_domain_triggers_no_task(self):
        from auth.api.routes.auth.settings import org_domain_submit

        tenant = _tenant()
        tenant.custom_domain = "acme.example.com"
        module = MagicMock()

        with (
            _authorised(tenant),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
            patch.dict("sys.modules", {"auth.tasks.custom_domain": module}),
        ):
            await org_domain_submit(
                _request(form_data={"custom_domain": "acme.example.com"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        module.verify_custom_domain_dns.delay.assert_not_called()
        module.remove_custom_domain_config.delay.assert_not_called()


# ---------------------------------------------------------------------------
# org_email_sender_submit / org_allowed_scopes_submit
# ---------------------------------------------------------------------------


class TestOrgEmailSenderSubmit:
    async def test_values_are_stored_and_the_cache_is_invalidated(self):
        from auth.api.routes.auth.settings import org_email_sender_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch("auth.tasks.email.invalidate_platform_sender_cache") as invalidate,
        ):
            result = await org_email_sender_submit(
                _request(
                    form_data={
                        "email_sender_address": " noreply@acme.test ",
                        "email_sender_name": "  ",
                    }
                ),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.settings["email_sender_address"] == "noreply@acme.test"
        assert tenant.settings["email_sender_name"] is None
        invalidate.assert_called_once()
        assert "success=Email+sender+updated" in result.headers["location"]


class TestOrgAllowedScopesSubmit:
    async def test_unknown_scope_is_rejected(self):
        from auth.api.routes.auth.settings import org_allowed_scopes_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[])),
        ):
            result = await org_allowed_scopes_submit(
                _request(form_data={"allowed_scopes": ["not:a:scope"]}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Invalid+scope" in result.headers["location"]

    async def test_valid_scopes_are_stored_sorted(self):
        from auth.api.routes.auth.settings import org_allowed_scopes_submit

        tenant = _tenant()
        scopes = [_scope("members:write"), _scope("members:read")]

        with (
            _authorised(tenant),
            patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=scopes)),
        ):
            result = await org_allowed_scopes_submit(
                _request(form_data={"allowed_scopes": ["members:write", "members:read"]}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.settings["allowed_scopes"] == ["members:read", "members:write"]
        assert "success=Allowed+scopes+updated" in result.headers["location"]

    async def test_empty_selection_clears_the_setting(self):
        from auth.api.routes.auth.settings import org_allowed_scopes_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[])),
        ):
            await org_allowed_scopes_submit(
                _request(form_data={}), str(tenant.id), AsyncMock(), AsyncMock()
            )

        assert tenant.settings["allowed_scopes"] is None


# ---------------------------------------------------------------------------
# org_verify_domain / org_domain_status
# ---------------------------------------------------------------------------


class TestOrgVerifyDomain:
    async def test_no_domain_configured(self):
        from auth.api.routes.auth.settings import org_verify_domain

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_verify_domain(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        assert "error=No+custom+domain+configured" in result.headers["location"]

    async def test_active_domain_reports_success(self):
        from auth.api.routes.auth.settings import org_verify_domain
        from auth.db.models.tenant import CustomDomainStatus

        tenant = _tenant()
        tenant.custom_domain = "acme.example.com"
        tenant.custom_domain_status = CustomDomainStatus.ACTIVE

        with _authorised(tenant):
            result = await org_verify_domain(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        assert "success=Domain+is+already+active" in result.headers["location"]

    @pytest.mark.parametrize("state", ["SSL_PROVISIONING", "DNS_VERIFYING"])
    async def test_in_flight_verification_is_reported(self, state):
        from auth.api.routes.auth.settings import org_verify_domain
        from auth.db.models.tenant import CustomDomainStatus

        tenant = _tenant()
        tenant.custom_domain = "acme.example.com"
        tenant.custom_domain_status = getattr(CustomDomainStatus, state)

        with _authorised(tenant):
            result = await org_verify_domain(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        assert "already+in+progress" in result.headers["location"]

    async def test_verification_is_started(self):
        from auth.api.routes.auth.settings import org_verify_domain
        from auth.db.models.tenant import CustomDomainStatus

        tenant = _tenant()
        tenant.custom_domain = "acme.example.com"
        tenant.custom_domain_status = CustomDomainStatus.FAILED
        verify = MagicMock()

        with (
            _authorised(tenant),
            patch.dict(
                "sys.modules",
                {"auth.tasks.custom_domain": MagicMock(verify_custom_domain_dns=verify)},
            ),
        ):
            result = await org_verify_domain(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        assert tenant.custom_domain_status is CustomDomainStatus.PENDING
        verify.delay.assert_called_once()
        assert "success=Domain+verification+started" in result.headers["location"]


class TestOrgDomainStatus:
    async def test_reports_the_null_state(self):
        from auth.api.routes.auth.settings import org_domain_status

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_domain_status(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        assert result == {
            "custom_domain": None,
            "status": None,
            "error": None,
            "verified_at": None,
            "ssl_at": None,
            "checked_at": None,
        }

    async def test_reports_a_populated_state(self):
        from auth.api.routes.auth.settings import org_domain_status
        from auth.db.models.tenant import CustomDomainStatus

        moment = _now()
        tenant = _tenant()
        tenant.custom_domain = "acme.example.com"
        tenant.custom_domain_status = CustomDomainStatus.ACTIVE
        tenant.custom_domain_error = "none"
        tenant.custom_domain_verified_at = moment
        tenant.custom_domain_ssl_at = moment
        tenant.custom_domain_checked_at = moment

        with _authorised(tenant):
            result = await org_domain_status(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        assert result["status"] == CustomDomainStatus.ACTIVE.value
        assert result["verified_at"] == moment.isoformat()
        assert result["ssl_at"] == moment.isoformat()
        assert result["checked_at"] == moment.isoformat()


# ---------------------------------------------------------------------------
# org_add_member_submit
# ---------------------------------------------------------------------------


class TestOrgAddMemberSubmit:
    async def test_email_is_required(self):
        from auth.api.routes.auth.settings import org_add_member_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_add_member_submit(
                _request(form_data={}), str(tenant.id), AsyncMock(), AsyncMock()
            )

        assert "error=Email+is+required" in result.headers["location"]

    async def test_role_from_another_org_is_rejected(self):
        from auth.api.routes.auth.settings import org_add_member_submit

        tenant = _tenant()
        foreign = _role(tenant_id=uuid.uuid4())

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=foreign),
            ),
        ):
            result = await org_add_member_submit(
                _request(form_data={"email": "b@example.com", "role_id": str(uuid.uuid4())}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Invalid+role" in result.headers["location"]

    async def test_role_name_fallback_is_used(self):
        from auth.api.routes.auth.settings import org_add_member_submit

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_name",
                AsyncMock(return_value=role),
            ) as by_name,
            patch(f"{MODULE}._user_service.get_user_email_row", AsyncMock(return_value=None)),
        ):
            result = await org_add_member_submit(
                _request(form_data={"email": "b@example.com", "role": "member"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        by_name.assert_awaited()
        assert "User+not+found" in result.headers["location"]

    async def test_unknown_role_falls_back_to_member(self):
        from auth.api.routes.auth.settings import org_add_member_submit

        tenant = _tenant()
        default_role = _role(tenant_id=tenant.id)

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=None)),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_name",
                AsyncMock(return_value=default_role),
            ) as by_name,
            patch(f"{MODULE}._user_service.get_user_email_row", AsyncMock(return_value=None)),
        ):
            await org_add_member_submit(
                _request(form_data={"email": "b@example.com", "role_id": str(uuid.uuid4())}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert by_name.await_args[0][2] == "member"

    async def test_existing_member_is_rejected(self):
        from auth.api.routes.auth.settings import org_add_member_submit

        tenant = _tenant()
        email_row = MagicMock()
        email_row.user_id = uuid.uuid4()
        email_row.email = "b@example.com"

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=_role(tenant_id=tenant.id)),
            ),
            patch(f"{MODULE}._user_service.get_user_email_row", AsyncMock(return_value=email_row)),
            patch(
                f"{MODULE}.tenant_service.get_existing_membership",
                AsyncMock(return_value=MagicMock()),
            ),
        ):
            result = await org_add_member_submit(
                _request(form_data={"email": "b@example.com", "role_id": str(uuid.uuid4())}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=User+is+already+a+member" in result.headers["location"]

    async def test_member_is_added(self):
        from auth.api.routes.auth.settings import org_add_member_submit

        tenant = _tenant()
        email_row = MagicMock()
        email_row.user_id = uuid.uuid4()
        email_row.email = "b@example.com"

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=_role(tenant_id=tenant.id)),
            ),
            patch(f"{MODULE}._user_service.get_user_email_row", AsyncMock(return_value=email_row)),
            patch(
                f"{MODULE}.tenant_service.get_existing_membership",
                AsyncMock(return_value=None),
            ),
            patch(f"{MODULE}.tenant_service.add_member", AsyncMock()) as add_member,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()) as dispatch,
        ):
            result = await org_add_member_submit(
                _request(form_data={"email": "b@example.com", "role_id": str(uuid.uuid4())}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        add_member.assert_awaited_once()
        dispatch.assert_awaited_once()
        assert "success=Member+added+successfully" in result.headers["location"]


# ---------------------------------------------------------------------------
# org_update_member_role_submit
# ---------------------------------------------------------------------------


class TestOrgUpdateMemberRole:
    async def test_unparseable_member_id_is_reported(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_update_member_role_submit(
                _request(form_data={}), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+member+ID" in result.headers["location"]

    async def test_missing_member_is_reported(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_member_in_tenant", AsyncMock(return_value=None)),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Member+not+found" in result.headers["location"]

    async def test_unknown_role_is_reported(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=_member(tenant.id)),
            ),
            patch(f"{MODULE}.tenant_role_service.get_role_by_name", AsyncMock(return_value=None)),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role": "ghost"}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Invalid+role" in result.headers["location"]

    async def test_role_from_another_org_is_rejected(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=_member(tenant.id)),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=_role(tenant_id=uuid.uuid4())),
            ),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role_id": str(uuid.uuid4())}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "does+not+belong" in result.headers["location"]

    async def test_non_owner_cannot_promote_to_owner(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()
        actor = _member(tenant.id, scopes=("members:write",))

        with (
            _authorised(tenant, actor),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=_member(tenant.id, scopes=("members:read",))),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=_role(scopes=("*",), tenant_id=tenant.id)),
            ),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role_id": str(uuid.uuid4())}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Only+owners+can+promote" in result.headers["location"]

    async def test_non_owner_cannot_change_an_owners_role(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()
        actor = _member(tenant.id, scopes=("members:write",))

        with (
            _authorised(tenant, actor),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=_member(tenant.id, scopes=("*",))),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=_role(tenant_id=tenant.id)),
            ),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role_id": str(uuid.uuid4())}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Only+owners+can+change" in result.headers["location"]

    async def test_the_only_owner_cannot_be_demoted(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()
        target = _member(tenant.id, scopes=("*",))

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=target),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=_role(tenant_id=tenant.id)),
            ),
            patch(f"{MODULE}.tenant_service.list_members", AsyncMock(return_value=[target])),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role_id": str(uuid.uuid4())}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Cannot+demote+the+only+owner" in result.headers["location"]

    async def test_role_is_assigned(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()
        target = _member(tenant.id)
        new_role = _role(name="admin", tenant_id=tenant.id)

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=target),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=new_role),
            ),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()) as dispatch,
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role_id": str(uuid.uuid4())}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert target.role_id == new_role.id
        dispatch.assert_awaited_once()
        assert "success=Member+role+updated" in result.headers["location"]


# ---------------------------------------------------------------------------
# org_remove_member_submit
# ---------------------------------------------------------------------------


class TestOrgRemoveMember:
    async def test_unparseable_member_id_is_reported(self):
        from auth.api.routes.auth.settings import org_remove_member_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_remove_member_submit(
                _request(), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+member+ID" in result.headers["location"]

    async def test_missing_member_is_reported(self):
        from auth.api.routes.auth.settings import org_remove_member_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_member_in_tenant", AsyncMock(return_value=None)),
        ):
            result = await org_remove_member_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Member+not+found" in result.headers["location"]

    async def test_non_owner_cannot_remove_an_owner(self):
        from auth.api.routes.auth.settings import org_remove_member_submit

        tenant = _tenant()
        actor = _member(tenant.id, scopes=("members:write",))

        with (
            _authorised(tenant, actor),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=_member(tenant.id, scopes=("*",))),
            ),
        ):
            result = await org_remove_member_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "Only+owners+can+remove" in result.headers["location"]

    async def test_the_only_owner_cannot_be_removed(self):
        from auth.api.routes.auth.settings import org_remove_member_submit

        tenant = _tenant()
        target = _member(tenant.id, scopes=("*",))

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=target),
            ),
            patch(f"{MODULE}.tenant_service.list_members", AsyncMock(return_value=[target])),
        ):
            result = await org_remove_member_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "Cannot+remove+the+only+owner" in result.headers["location"]

    async def test_member_is_removed(self):
        from auth.api.routes.auth.settings import org_remove_member_submit

        tenant = _tenant()
        target = _member(tenant.id)
        db = AsyncMock()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=target),
            ),
            patch(f"{MODULE}.tenant_service.remove_member", AsyncMock()) as remove,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()) as dispatch,
        ):
            result = await org_remove_member_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), db, AsyncMock()
            )

        remove.assert_awaited_once()
        dispatch.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert "success=Member+removed" in result.headers["location"]


# ---------------------------------------------------------------------------
# Role management
# ---------------------------------------------------------------------------


def _authorised_manager(tenant=None, membership=None, user=None):
    """Patch ``require_tenant_manager`` (used by the roles handlers)."""
    tenant = tenant or _tenant()
    membership = membership if membership is not None else _member(tenant.id, scopes=("*",))
    return patch(
        f"{MODULE}.require_tenant_manager",
        AsyncMock(return_value=(user or _user(), tenant, membership)),
    )


class TestOrgRolesPage:
    async def test_role_member_counts_are_collected(self):
        from auth.api.routes.auth.settings import org_roles_page

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)
        templates = MagicMock()
        request = _request()

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}.tenant_role_service.get_tenant_roles",
                AsyncMock(return_value=[role]),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_member_count",
                AsyncMock(return_value=4),
            ),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
        ):
            await org_roles_page(request, str(tenant.id), AsyncMock(), AsyncMock(), templates)

        # The request comes first: Starlette no longer accepts the template name there.
        assert templates.TemplateResponse.call_args[0][:2] == (
            request,
            "auth/settings/org/roles.html",
        )
        ctx = templates.TemplateResponse.call_args[0][2]
        assert ctx["role_stats"][str(role.id)] == 4
        assert ctx["can"]["roles:write"] is True


class TestOrgRoleCreatePage:
    async def test_renders_the_blank_form(self):
        from auth.api.routes.auth.settings import org_role_create_page

        tenant = _tenant()
        templates = MagicMock()
        request = _request()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.get_all_available_scopes", AsyncMock(return_value={})),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
        ):
            await org_role_create_page(request, str(tenant.id), AsyncMock(), AsyncMock(), templates)

        assert templates.TemplateResponse.call_args[0][:2] == (
            request,
            "auth/settings/org/role_form.html",
        )
        ctx = templates.TemplateResponse.call_args[0][2]
        assert ctx["role"] is None


class TestOrgRoleCreateSubmit:
    async def test_name_is_required(self):
        from auth.api.routes.auth.settings import org_role_create_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_role_create_submit(
                _request(form_data={}), str(tenant.id), AsyncMock(), AsyncMock()
            )

        assert "error=Role+name+is+required" in result.headers["location"]

    async def test_display_name_defaults_to_the_capitalised_name(self):
        from auth.api.routes.auth.settings import org_role_create_submit

        tenant = _tenant()
        role = _role(name="editor", tenant_id=tenant.id)

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}.tenant_role_service.create_role", AsyncMock(return_value=role)
            ) as create,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_role_create_submit(
                _request(form_data={"name": " EDITOR "}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert create.await_args[0][3] == "Editor"
        assert "created" in result.headers["location"]
        # The roles page, not a malformed path glued to the tenant id.
        assert result.headers["location"].startswith(f"/auth/settings/org/{tenant.id}/roles?")

    async def test_validation_error_is_reported(self):
        from auth.api.routes.auth.settings import org_role_create_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}.tenant_role_service.create_role",
                AsyncMock(side_effect=ValueError("Role already exists")),
            ),
        ):
            result = await org_role_create_submit(
                _request(form_data={"name": "editor", "display_name": "Editor"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Role+already+exists" in result.headers["location"]


class TestOrgRoleEditPage:
    async def test_unparseable_role_id_is_a_404(self):
        from auth.api.routes.auth.settings import org_role_edit_page
        from fastapi import HTTPException

        tenant = _tenant()

        with _authorised_manager(tenant), pytest.raises(HTTPException) as exc:
            await org_role_edit_page(
                _request(),
                str(tenant.id),
                "not-a-uuid",
                AsyncMock(),
                AsyncMock(),
                MagicMock(),
            )

        assert exc.value.status_code == 404

    async def test_role_from_another_org_is_a_404(self):
        from auth.api.routes.auth.settings import org_role_edit_page
        from fastapi import HTTPException

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=_role(tenant_id=uuid.uuid4())),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await org_role_edit_page(
                _request(),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
                MagicMock(),
            )

        assert exc.value.status_code == 404

    async def test_renders_the_populated_form(self):
        from auth.api.routes.auth.settings import org_role_edit_page

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)
        templates = MagicMock()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{MODULE}.get_all_available_scopes", AsyncMock(return_value={})),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
        ):
            await org_role_edit_page(
                _request(), str(tenant.id), str(role.id), AsyncMock(), AsyncMock(), templates
            )

        ctx = templates.TemplateResponse.call_args[0][2]
        assert ctx["role"] is role


class TestOrgRoleEditSubmit:
    async def test_unparseable_role_id_is_reported(self):
        from auth.api.routes.auth.settings import org_role_edit_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_role_edit_submit(
                _request(form_data={}), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+role+ID" in result.headers["location"]

    async def test_missing_role_is_reported(self):
        from auth.api.routes.auth.settings import org_role_edit_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=None)),
        ):
            result = await org_role_edit_submit(
                _request(form_data={}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Role+not+found" in result.headers["location"]

    async def test_default_flag_is_set(self):
        from auth.api.routes.auth.settings import org_role_edit_submit

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)
        role.is_default = False

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{MODULE}.tenant_role_service.update_role", AsyncMock()) as update,
            patch(f"{MODULE}.tenant_role_service.set_default_role", AsyncMock()) as set_default,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_role_edit_submit(
                _request(form_data={"display_name": "Editor", "is_default": "true"}),
                str(tenant.id),
                str(role.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert update.await_args[0][3] == []
        set_default.assert_awaited_once()
        assert "updated" in result.headers["location"]

    async def test_default_flag_is_cleared(self):
        from auth.api.routes.auth.settings import org_role_edit_submit

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)
        role.is_default = True

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{MODULE}.tenant_role_service.update_role", AsyncMock()),
            patch(f"{MODULE}.tenant_role_service.clear_default_role", AsyncMock()) as clear_default,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            await org_role_edit_submit(
                _request(form_data={"display_name": "Editor"}),
                str(tenant.id),
                str(role.id),
                AsyncMock(),
                AsyncMock(),
            )

        clear_default.assert_awaited_once()

    async def test_system_role_scopes_are_left_alone(self):
        from auth.api.routes.auth.settings import org_role_edit_submit

        tenant = _tenant()
        role = _role(tenant_id=tenant.id, is_system=True)
        role.is_default = False

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{MODULE}.tenant_role_service.update_role", AsyncMock()) as update,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            await org_role_edit_submit(
                _request(form_data={"display_name": "Owner", "scopes": ["members:write"]}),
                str(tenant.id),
                str(role.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert update.await_args[0][3] is None

    async def test_validation_error_is_reported(self):
        from auth.api.routes.auth.settings import org_role_edit_submit

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(
                f"{MODULE}.tenant_role_service.update_role",
                AsyncMock(side_effect=ValueError("Invalid scopes")),
            ),
        ):
            result = await org_role_edit_submit(
                _request(form_data={"display_name": "Editor"}),
                str(tenant.id),
                str(role.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Invalid+scopes" in result.headers["location"]


class TestOrgRoleDeleteSubmit:
    async def test_unparseable_role_id_is_reported(self):
        from auth.api.routes.auth.settings import org_role_delete_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_role_delete_submit(
                _request(), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+role+ID" in result.headers["location"]

    async def test_missing_role_is_reported(self):
        from auth.api.routes.auth.settings import org_role_delete_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=None)),
        ):
            result = await org_role_delete_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Role+not+found" in result.headers["location"]

    async def test_role_is_deleted(self):
        from auth.api.routes.auth.settings import org_role_delete_submit

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{MODULE}.tenant_role_service.delete_role", AsyncMock()) as delete,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_role_delete_submit(
                _request(), str(tenant.id), str(role.id), AsyncMock(), AsyncMock()
            )

        delete.assert_awaited_once()
        assert "deleted" in result.headers["location"]

    async def test_deletion_error_is_reported(self):
        from auth.api.routes.auth.settings import org_role_delete_submit

        tenant = _tenant()
        role = _role(tenant_id=tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(
                f"{MODULE}.tenant_role_service.delete_role",
                AsyncMock(side_effect=ValueError("Role is in use")),
            ),
        ):
            result = await org_role_delete_submit(
                _request(), str(tenant.id), str(role.id), AsyncMock(), AsyncMock()
            )

        assert "Role+is+in+use" in result.headers["location"]


# ---------------------------------------------------------------------------
# Identity providers
# ---------------------------------------------------------------------------


def _idp(tenant_id=None, secret=b"enc"):
    from auth.db.models.tenant import IdentityProviderType

    idp = MagicMock()
    idp.id = uuid.uuid4()
    idp.tenant_id = tenant_id or uuid.uuid4()
    idp.name = "Google SSO"
    idp.provider_type = IdentityProviderType.OIDC
    idp.client_id = "cid"
    idp.client_secret_encrypted = secret
    idp.discovery_url = "https://idp/.well-known/openid-configuration"
    idp.scopes = ["openid"]
    idp.is_active = True
    idp.is_default = False
    idp.auto_provision = True
    idp.allow_linking = True
    idp.icon_url = None
    idp.button_text = "Sign in"
    idp.display_order = 0
    idp.federated_identities = []
    idp.created_at = _now()
    idp.updated_at = _now()
    return idp


class TestOrgIdpCreatePage:
    async def test_renders_the_form(self):
        from auth.api.routes.auth.settings import org_idp_create_page

        tenant = _tenant()
        templates, page_patches = _patch_page()

        _entered, close = _enter((*page_patches, _authorised(tenant)))
        try:
            await org_idp_create_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        templates.TemplateResponse.assert_called_once()


class TestOrgIdpCreateSubmit:
    async def test_name_and_client_id_are_required(self):
        from auth.api.routes.auth.settings import org_idp_create_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_idp_create_submit(
                _request(form_data={"name": "IdP"}), str(tenant.id), AsyncMock(), AsyncMock()
            )

        assert "Name+and+Client+ID+are+required" in result.headers["location"]

    async def test_unknown_provider_type_falls_back_to_oidc(self):
        from auth.api.routes.auth.settings import org_idp_create_submit
        from auth.db.models.tenant import IdentityProviderType

        tenant = _tenant()
        staged = {}

        async def _add(_db, idp):
            staged["idp"] = idp
            idp.id = uuid.uuid4()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.add_idp", AsyncMock(side_effect=_add)),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_idp_create_submit(
                _request(
                    form_data={
                        "name": "IdP",
                        "client_id": "cid",
                        "provider_type": "carrier-pigeon",
                    }
                ),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert staged["idp"].provider_type is IdentityProviderType.OIDC
        assert staged["idp"].client_secret_encrypted is None
        assert "success=Identity+provider+created" in result.headers["location"]

    async def test_client_secret_is_encrypted(self):
        from auth.api.routes.auth.settings import org_idp_create_submit

        tenant = _tenant()
        staged = {}
        encryption = MagicMock()
        encryption.encrypt.return_value = b"cipher"

        async def _add(_db, idp):
            staged["idp"] = idp
            idp.id = uuid.uuid4()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.add_idp", AsyncMock(side_effect=_add)),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
            patch(f"{MODULE}.get_encryption", return_value=encryption),
        ):
            await org_idp_create_submit(
                _request(form_data={"name": "IdP", "client_id": "cid", "client_secret": "s3cr3t"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        encryption.encrypt.assert_called_once_with(b"s3cr3t")
        assert staged["idp"].client_secret_encrypted == b"cipher"

    async def test_persistence_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_create_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.add_idp",
                AsyncMock(side_effect=RuntimeError("db down")),
            ),
        ):
            result = await org_idp_create_submit(
                _request(form_data={"name": "IdP", "client_id": "cid"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "db+down" in result.headers["location"]


class TestOrgIdpEditPage:
    async def test_unparseable_idp_id_is_a_404(self):
        from auth.api.routes.auth.settings import org_idp_edit_page
        from fastapi import HTTPException

        tenant = _tenant()
        _templates, page_patches = _patch_page()

        _entered, close = _enter((*page_patches, _authorised(tenant)))
        try:
            with pytest.raises(HTTPException) as exc:
                await org_idp_edit_page(
                    _request(), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
                )
        finally:
            close()

        assert exc.value.status_code == 404

    async def test_missing_idp_is_a_404(self):
        from auth.api.routes.auth.settings import org_idp_edit_page
        from fastapi import HTTPException

        tenant = _tenant()
        _templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(
                    f"{MODULE}.tenant_service.get_idp_scoped_with_federated",
                    AsyncMock(return_value=None),
                ),
            )
        )
        try:
            with pytest.raises(HTTPException) as exc:
                await org_idp_edit_page(
                    _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
                )
        finally:
            close()

        assert exc.value.status_code == 404

    async def test_renders_secret_and_link_counts(self):
        from auth.api.routes.auth.settings import org_idp_edit_page

        tenant = _tenant()
        idp = _idp(tenant.id)
        idp.federated_identities = [MagicMock(), MagicMock()]
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(
                    f"{MODULE}.tenant_service.get_idp_scoped_with_federated",
                    AsyncMock(return_value=idp),
                ),
            )
        )
        try:
            await org_idp_edit_page(
                _request(), str(tenant.id), str(idp.id), AsyncMock(), AsyncMock()
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["idp"]["has_secret"] is True
        assert ctx["idp"]["federated_count"] == 2


class TestOrgIdpEditSubmit:
    async def test_unparseable_idp_id_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_edit_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_idp_edit_submit(
                _request(form_data={}), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+IdP+ID" in result.headers["location"]

    async def test_missing_idp_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_edit_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=None)),
        ):
            result = await org_idp_edit_submit(
                _request(form_data={}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Identity+provider+not+found" in result.headers["location"]

    async def test_name_and_client_id_are_required(self):
        from auth.api.routes.auth.settings import org_idp_edit_submit

        tenant = _tenant()
        idp = _idp(tenant.id)

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=idp)),
        ):
            result = await org_idp_edit_submit(
                _request(form_data={"name": "IdP"}),
                str(tenant.id),
                str(idp.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Name+and+Client+ID+are+required" in result.headers["location"]

    async def test_new_secret_is_encrypted(self):
        from auth.api.routes.auth.settings import org_idp_edit_submit

        tenant = _tenant()
        idp = _idp(tenant.id)
        encryption = MagicMock()
        encryption.encrypt.return_value = b"cipher"

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=idp)),
            patch(f"{MODULE}.get_encryption", return_value=encryption),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_idp_edit_submit(
                _request(form_data={"name": "IdP", "client_id": "cid", "client_secret": "rotated"}),
                str(tenant.id),
                str(idp.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert idp.client_secret_encrypted == b"cipher"
        assert "success=Identity+provider+updated" in result.headers["location"]

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_edit_submit

        tenant = _tenant()
        idp = _idp(tenant.id)
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=idp)),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_idp_edit_submit(
                _request(form_data={"name": "IdP", "client_id": "cid"}),
                str(tenant.id),
                str(idp.id),
                db,
                AsyncMock(),
            )

        assert "db+down" in result.headers["location"]


class TestOrgIdpToggle:
    async def test_unparseable_idp_id_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_toggle_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_idp_toggle_submit(
                _request(), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+IdP+ID" in result.headers["location"]

    async def test_missing_idp_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_toggle_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=None)),
        ):
            result = await org_idp_toggle_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Identity+provider+not+found" in result.headers["location"]

    @pytest.mark.parametrize(("initial", "word"), [(True, "disabled"), (False, "enabled")])
    async def test_toggle_reports_the_new_state(self, initial, word):
        from auth.api.routes.auth.settings import org_idp_toggle_submit

        tenant = _tenant()
        idp = _idp(tenant.id)
        idp.is_active = initial

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=idp)),
        ):
            result = await org_idp_toggle_submit(
                _request(), str(tenant.id), str(idp.id), AsyncMock(), AsyncMock()
            )

        assert idp.is_active is not initial
        assert f"Identity+provider+{word}" in result.headers["location"]


class TestOrgIdpDelete:
    async def test_unparseable_idp_id_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_delete_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_idp_delete_submit(
                _request(), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+IdP+ID" in result.headers["location"]

    async def test_missing_idp_is_reported(self):
        from auth.api.routes.auth.settings import org_idp_delete_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=None)),
        ):
            result = await org_idp_delete_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Identity+provider+not+found" in result.headers["location"]

    async def test_idp_is_deleted(self):
        from auth.api.routes.auth.settings import org_idp_delete_submit

        tenant = _tenant()
        idp = _idp(tenant.id)
        db = AsyncMock()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_idp_scoped", AsyncMock(return_value=idp)),
            patch(f"{MODULE}.tenant_service.delete_idp", AsyncMock()) as delete,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()) as dispatch,
        ):
            result = await org_idp_delete_submit(
                _request(), str(tenant.id), str(idp.id), db, AsyncMock()
            )

        delete.assert_awaited_once()
        dispatch.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert "success=Identity+provider+deleted" in result.headers["location"]


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------


def _branding():
    branding = MagicMock()
    branding.tenant_id = uuid.uuid4()
    for attr in (
        "logo_url",
        "logo_dark_url",
        "favicon_url",
        "input_background_color",
        "input_focus_background_color",
        "input_border_color",
        "input_focus_border_color",
        "input_text_color",
        "font_url",
        "custom_css",
        "custom_js",
    ):
        setattr(branding, attr, None)
    branding.primary_color = "#111111"
    branding.secondary_color = "#222222"
    branding.accent_color = "#333333"
    branding.background_color = "#444444"
    branding.surface_color = "#555555"
    branding.text_color = "#666666"
    branding.text_muted_color = "#777777"
    branding.error_color = "#888888"
    branding.success_color = "#999999"
    branding.border_color = "#aaaaaa"
    branding.warning_color = "#bbbbbb"
    branding.info_color = "#cccccc"
    branding.font_family = "sans-serif"
    branding.show_powered_by = True
    return branding


class TestOrgBrandingPage:
    async def test_missing_branding_falls_back_to_defaults(self):
        from auth.api.routes.auth.settings import org_branding_page
        from auth.services.branding import BrandingConfig

        tenant = _tenant()
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(
                    f"{MODULE}.tenant_service.get_by_id_with_branding",
                    AsyncMock(return_value=tenant),
                ),
            )
        )
        try:
            await org_branding_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["has_branding"] is False
        assert ctx["tenant_branding"]["primary_color"] == BrandingConfig().primary_color

    async def test_existing_branding_is_used(self):
        from auth.api.routes.auth.settings import org_branding_page

        tenant = _tenant(branding=_branding())
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(
                    f"{MODULE}.tenant_service.get_by_id_with_branding",
                    AsyncMock(return_value=tenant),
                ),
            )
        )
        try:
            await org_branding_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["has_branding"] is True
        assert ctx["tenant_branding"]["primary_color"] == "#111111"


class TestOrgBrandingSubmit:
    async def test_missing_branding_row_is_created(self):
        from auth.api.routes.auth.settings import org_branding_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_by_id_with_branding",
                AsyncMock(return_value=tenant),
            ),
            patch(f"{MODULE}.tenant_service.add_branding", AsyncMock()) as add,
        ):
            result = await org_branding_submit(
                _request(form_data={"primary_color": "#123456", "show_powered_by": "true"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        add.assert_awaited_once()
        created = add.await_args[0][1]
        assert created.primary_color == "#123456"
        assert created.show_powered_by is True
        assert "success=Branding+updated" in result.headers["location"]

    async def test_blank_fields_fall_back_to_defaults(self):
        from auth.api.routes.auth.settings import org_branding_submit

        branding = _branding()
        tenant = _tenant(branding=branding)

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_by_id_with_branding",
                AsyncMock(return_value=tenant),
            ),
        ):
            await org_branding_submit(
                _request(form_data={"logo_url": "  ", "font_family": "  "}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert branding.logo_url is None
        assert branding.primary_color == "#007bff"
        assert branding.font_family.startswith("-apple-system")
        assert branding.show_powered_by is False

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_branding_submit

        tenant = _tenant(branding=_branding())
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_by_id_with_branding",
                AsyncMock(return_value=tenant),
            ),
        ):
            result = await org_branding_submit(
                _request(form_data={}), str(tenant.id), db, AsyncMock()
            )

        assert "db+down" in result.headers["location"]


class TestOrgBrandingReset:
    async def test_existing_branding_is_deleted(self):
        from auth.api.routes.auth.settings import org_branding_reset

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_branding",
                AsyncMock(return_value=_branding()),
            ),
            patch(f"{MODULE}.tenant_service.delete_branding", AsyncMock()) as delete,
        ):
            result = await org_branding_reset(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        delete.assert_awaited_once()
        assert "success=Branding+reset" in result.headers["location"]

    async def test_absent_branding_is_a_no_op(self):
        from auth.api.routes.auth.settings import org_branding_reset

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_branding", AsyncMock(return_value=None)),
            patch(f"{MODULE}.tenant_service.delete_branding", AsyncMock()) as delete,
        ):
            result = await org_branding_reset(_request(), str(tenant.id), AsyncMock(), AsyncMock())

        delete.assert_not_awaited()
        assert result.status_code == 303


# ---------------------------------------------------------------------------
# Registration / profile field editors
# ---------------------------------------------------------------------------


class TestOrgFieldPages:
    async def test_registration_fields_defaults_and_overrides(self):
        from auth.api.routes.auth.settings import (
            _ORG_REGISTRATION_FIELD_KEYS,
            org_registration_fields_page,
        )

        key = _ORG_REGISTRATION_FIELD_KEYS[0]
        tenant = _tenant(settings={"registration_fields": {key: False}})
        templates, page_patches = _patch_page()

        _entered, close = _enter((*page_patches, _authorised(tenant)))
        try:
            await org_registration_fields_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        fields = templates.TemplateResponse.call_args.kwargs["context"]["fields"]
        assert fields[key] is False
        assert all(v is True for k, v in fields.items() if k != key)

    async def test_profile_fields_defaults_and_overrides(self):
        from auth.api.routes.auth.settings import (
            DEFAULT_PROFILE_FIELDS,
            org_profile_fields_page,
        )

        key = next(iter(DEFAULT_PROFILE_FIELDS))
        tenant = _tenant(settings={"profile_fields": {key: False}})
        templates, page_patches = _patch_page()

        _entered, close = _enter((*page_patches, _authorised(tenant)))
        try:
            await org_profile_fields_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        fields = templates.TemplateResponse.call_args.kwargs["context"]["fields"]
        assert fields[key] is False
        assert all(v is DEFAULT_PROFILE_FIELDS[k] for k, v in fields.items() if k != key)


class TestOrgFieldSubmits:
    async def test_registration_fields_are_persisted(self):
        from auth.api.routes.auth.settings import (
            _ORG_REGISTRATION_FIELD_KEYS,
            org_registration_fields_submit,
        )

        tenant = _tenant()
        enabled = _ORG_REGISTRATION_FIELD_KEYS[0]

        with _authorised(tenant), patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            result = await org_registration_fields_submit(
                _request(form_data={enabled: "true"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.settings["registration_fields"][enabled] is True
        assert "success=Registration+fields+updated" in result.headers["location"]

    async def test_registration_fields_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_registration_fields_submit

        tenant = _tenant()
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with _authorised(tenant), patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            result = await org_registration_fields_submit(
                _request(form_data={}), str(tenant.id), db, AsyncMock()
            )

        assert "error=db down" in result.headers["location"].replace("%20", " ")

    async def test_profile_fields_are_persisted(self):
        from auth.api.routes.auth.settings import (
            _PROFILE_FIELD_KEYS,
            org_profile_fields_submit,
        )

        tenant = _tenant()
        enabled = _PROFILE_FIELD_KEYS[0]

        with _authorised(tenant), patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            result = await org_profile_fields_submit(
                _request(form_data={enabled: "true"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.settings["profile_fields"][enabled] is True
        assert "success=Profile+fields+updated" in result.headers["location"]

    async def test_profile_fields_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_profile_fields_submit

        tenant = _tenant()
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with _authorised(tenant), patch(f"{MODULE}.get_tenant_prefix", return_value=""):
            result = await org_profile_fields_submit(
                _request(form_data={}), str(tenant.id), db, AsyncMock()
            )

        assert "error=db down" in result.headers["location"].replace("%20", " ")


# ---------------------------------------------------------------------------
# OAuth2 clients
# ---------------------------------------------------------------------------


def _client(tenant_id=None, is_confidential=True):
    client = MagicMock()
    client.id = uuid.uuid4()
    client.client_id = "cid"
    client.name = "My App"
    client.description = None
    client.homepage_url = None
    client.redirect_uris = ["https://app.example.com/cb"]
    client.allowed_scopes = ["openid"]
    client.allowed_grant_types = ["authorization_code"]
    client.token_endpoint_auth_method = "client_secret_basic"
    client.is_confidential = is_confidential
    client.is_active = True
    client.require_pkce = True
    client.require_consent = True
    client.allowed_origins = None
    client.access_token_expiry_seconds = None
    client.refresh_token_expiry_seconds = None
    client.tenant_id = tenant_id or uuid.uuid4()
    client.created_at = _now()
    return client


class TestGetOrgClient:
    async def test_unparseable_id_is_a_404(self):
        from auth.api.routes.auth.settings import _get_org_client
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await _get_org_client(AsyncMock(), "not-a-uuid", uuid.uuid4())

        assert exc.value.status_code == 404

    async def test_missing_client_is_a_404(self):
        from auth.api.routes.auth.settings import _get_org_client
        from fastapi import HTTPException

        with (
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=None),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await _get_org_client(AsyncMock(), str(uuid.uuid4()), uuid.uuid4())

        assert exc.value.status_code == 404


class TestOrgClientPages:
    async def test_list_page_renders_tenant_clients(self):
        from auth.api.routes.auth.settings import org_clients_page

        tenant = _tenant()
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised_manager(tenant),
                patch(
                    f"{MODULE}._oauth2_client_service.list",
                    AsyncMock(return_value=([_client(tenant.id)], 1)),
                ),
            )
        )
        try:
            await org_clients_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["clients"][0]["client_id"] == "cid"

    async def test_create_page_restricts_scopes_to_the_tenant_allow_list(self):
        from auth.api.routes.auth.settings import org_client_create_page

        tenant = _tenant(settings={"allowed_scopes": ["openid"]})
        _templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised_manager(tenant),
                patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[])),
            )
        )
        try:
            await org_client_create_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

    async def test_detail_page_surfaces_a_new_secret(self):
        from auth.api.routes.auth.settings import org_client_detail_page

        tenant = _tenant()
        client = _client(tenant.id)
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised_manager(tenant),
                patch(
                    f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                    AsyncMock(return_value=client),
                ),
            )
        )
        try:
            await org_client_detail_page(
                _request(query_params={"new_secret": "s3cr3t"}),
                str(tenant.id),
                str(client.id),
                AsyncMock(),
                AsyncMock(),
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["new_secret"] == "s3cr3t"

    async def test_edit_page_renders_scope_groups(self):
        from auth.api.routes.auth.settings import org_client_edit_page

        tenant = _tenant()
        client = _client(tenant.id)
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised_manager(tenant),
                patch(
                    f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                    AsyncMock(return_value=client),
                ),
                patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[])),
            )
        )
        try:
            await org_client_edit_page(
                _request(), str(tenant.id), str(client.id), AsyncMock(), AsyncMock()
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["client"]["client_id"] == "cid"


class TestOrgClientCreateSubmit:
    async def test_name_is_required(self):
        from auth.api.routes.auth.settings import org_client_create_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_client_create_submit(
                _request(form_data={}), str(tenant.id), AsyncMock(), AsyncMock()
            )

        assert "error=Client+name+is+required" in result.headers["location"]

    async def test_confidential_client_returns_its_secret_once(self):
        from auth.api.routes.auth.settings import org_client_create_submit

        tenant = _tenant()
        staged = {}

        async def _add(_db, client):
            staged["client"] = client
            client.id = uuid.uuid4()

        form = {
            "name": "My App",
            "redirect_uris": "https://app.example.com/cb\nhttps://app.example.com/cb2",
            "allowed_origins": "https://app.example.com",
            "scope_openid": "true",
            "grant_authorization_code": "true",
            "is_confidential": "true",
            "access_token_expiry_seconds": "600",
            "refresh_token_expiry_seconds": "1200",
        }

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._oauth2_client_service.add", AsyncMock(side_effect=_add)),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_client_create_submit(
                _request(form_data=form), str(tenant.id), AsyncMock(), AsyncMock()
            )

        created = staged["client"]
        assert created.redirect_uris == [
            "https://app.example.com/cb",
            "https://app.example.com/cb2",
        ]
        assert created.allowed_scopes == ["openid"]
        assert created.allowed_grant_types == ["authorization_code"]
        assert created.allowed_origins == ["https://app.example.com"]
        assert created.access_token_expiry_seconds == 600
        assert created.refresh_token_expiry_seconds == 1200
        assert created.token_endpoint_auth_method == "client_secret_basic"
        assert "new_secret=" in result.headers["location"]

    async def test_public_client_gets_no_secret(self):
        from auth.api.routes.auth.settings import org_client_create_submit

        tenant = _tenant()
        staged = {}

        async def _add(_db, client):
            staged["client"] = client
            client.id = uuid.uuid4()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._oauth2_client_service.add", AsyncMock(side_effect=_add)),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_client_create_submit(
                _request(form_data={"name": "My App"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert staged["client"].client_secret_hash is None
        assert staged["client"].token_endpoint_auth_method == "none"
        assert staged["client"].allowed_origins is None
        assert "new_secret=" not in result.headers["location"]

    async def test_persistence_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_client_create_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.add",
                AsyncMock(side_effect=RuntimeError("db down")),
            ),
        ):
            result = await org_client_create_submit(
                _request(form_data={"name": "My App"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "db+down" in result.headers["location"]


class TestOrgClientEditSubmit:
    async def test_name_is_required(self):
        from auth.api.routes.auth.settings import org_client_edit_submit

        tenant = _tenant()
        client = _client(tenant.id)

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_edit_submit(
                _request(form_data={}),
                str(tenant.id),
                str(client.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Client+name+is+required" in result.headers["location"]

    async def test_public_to_confidential_issues_a_secret(self):
        from auth.api.routes.auth.settings import org_client_edit_submit

        tenant = _tenant()
        client = _client(tenant.id, is_confidential=False)

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_edit_submit(
                _request(form_data={"name": "My App", "is_confidential": "true"}),
                str(tenant.id),
                str(client.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert client.is_confidential is True
        assert client.token_endpoint_auth_method == "client_secret_basic"
        assert "new_secret=" in result.headers["location"]

    async def test_confidential_to_public_drops_the_secret(self):
        from auth.api.routes.auth.settings import org_client_edit_submit

        tenant = _tenant()
        client = _client(tenant.id, is_confidential=True)

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_edit_submit(
                _request(form_data={"name": "My App"}),
                str(tenant.id),
                str(client.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert client.is_confidential is False
        assert client.client_secret_hash is None
        assert client.token_endpoint_auth_method == "none"
        assert "new_secret=" not in result.headers["location"]

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_client_edit_submit

        tenant = _tenant()
        client = _client(tenant.id)
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_edit_submit(
                _request(form_data={"name": "My App"}),
                str(tenant.id),
                str(client.id),
                db,
                AsyncMock(),
            )

        assert "db+down" in result.headers["location"]


class TestOrgClientLifecycle:
    async def test_disable(self):
        from auth.api.routes.auth.settings import org_client_disable

        tenant = _tenant()
        client = _client(tenant.id)

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_disable(
                _request(), str(tenant.id), str(client.id), AsyncMock(), AsyncMock()
            )

        assert client.is_active is False
        assert "success=Client+disabled" in result.headers["location"]

    async def test_enable(self):
        from auth.api.routes.auth.settings import org_client_enable

        tenant = _tenant()
        client = _client(tenant.id)
        client.is_active = False

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_enable(
                _request(), str(tenant.id), str(client.id), AsyncMock(), AsyncMock()
            )

        assert client.is_active is True
        assert "success=Client+enabled" in result.headers["location"]

    async def test_rotate_secret_on_a_public_client_is_rejected(self):
        from auth.api.routes.auth.settings import org_client_rotate_secret

        tenant = _tenant()
        client = _client(tenant.id, is_confidential=False)

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_rotate_secret(
                _request(), str(tenant.id), str(client.id), AsyncMock(), AsyncMock()
            )

        assert "public+client" in result.headers["location"]

    async def test_rotate_secret(self):
        from auth.api.routes.auth.settings import org_client_rotate_secret

        tenant = _tenant()
        client = _client(tenant.id)
        old_hash = client.client_secret_hash

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_rotate_secret(
                _request(), str(tenant.id), str(client.id), AsyncMock(), AsyncMock()
            )

        assert client.client_secret_hash != old_hash
        assert "new_secret=" in result.headers["location"]

    async def test_delete(self):
        from auth.api.routes.auth.settings import org_client_delete

        tenant = _tenant()
        client = _client(tenant.id)
        db = AsyncMock()

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
            patch(f"{MODULE}._oauth2_client_service.delete", AsyncMock()) as delete,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()) as dispatch,
        ):
            result = await org_client_delete(
                _request(), str(tenant.id), str(client.id), db, AsyncMock()
            )

        delete.assert_awaited_once()
        dispatch.assert_awaited_once()
        assert "success=Client+deleted" in result.headers["location"]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def _template_row(name="auth/login.html", is_active=True):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.template_name = name
    row.description = "desc"
    row.content = "<p>hi</p>"
    row.is_active = is_active
    row.created_at = _now()
    row.updated_at = _now()
    return row


def _customizable():
    from auth.services.branding import BrandingService

    return next(iter(BrandingService.CUSTOMIZABLE_TEMPLATES))


def _customizable_mjml():
    from auth.services.branding import BrandingService

    name = next((t for t in BrandingService.CUSTOMIZABLE_TEMPLATES if t.endswith(".mjml")), None)
    if name is None:
        pytest.skip("no customizable MJML template in this build")
    return name


class TestOrgTemplatesPage:
    async def test_templates_are_sorted_by_name(self):
        from auth.api.routes.auth.settings import org_templates_page

        tenant = _tenant(templates=[_template_row("z.html"), _template_row("a.html")])
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(
                    f"{MODULE}.tenant_service.get_by_id_with_templates",
                    AsyncMock(return_value=tenant),
                ),
            )
        )
        try:
            await org_templates_page(_request(), str(tenant.id), AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert [t["template_name"] for t in ctx["tenant_templates"]] == ["a.html", "z.html"]


class TestOrgTemplateEditPage:
    async def test_non_customizable_template_is_a_400(self):
        from auth.api.routes.auth.settings import org_template_edit_page
        from fastapi import HTTPException

        tenant = _tenant()
        _templates, page_patches = _patch_page()

        _entered, close = _enter((*page_patches, _authorised(tenant)))
        try:
            with pytest.raises(HTTPException) as exc:
                await org_template_edit_page(
                    _request(), str(tenant.id), "secret/internal.html", AsyncMock(), AsyncMock()
                )
        finally:
            close()

        assert exc.value.status_code == 400

    async def test_existing_override_is_rendered(self):
        from auth.api.routes.auth.settings import org_template_edit_page

        tenant = _tenant()
        name = _customizable()
        templates, page_patches = _patch_page()

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(
                    f"{MODULE}.tenant_service.get_template",
                    AsyncMock(return_value=_template_row(name)),
                ),
            )
        )
        try:
            await org_template_edit_page(_request(), str(tenant.id), name, AsyncMock(), AsyncMock())
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["template"]["template_name"] == name
        assert isinstance(ctx["default_content"], str)

    async def test_absent_default_file_yields_empty_content(self):
        from auth.api.routes.auth.settings import org_template_edit_page

        tenant = _tenant()
        templates, page_patches = _patch_page()

        missing = MagicMock()
        missing.exists.return_value = False
        templates_dir = MagicMock()
        templates_dir.__truediv__ = MagicMock(return_value=missing)
        path_cls = MagicMock()
        path_cls.return_value.parent.parent.parent.parent.__truediv__ = MagicMock(
            return_value=templates_dir
        )

        _entered, close = _enter(
            (
                *page_patches,
                _authorised(tenant),
                patch(f"{MODULE}.tenant_service.get_template", AsyncMock(return_value=None)),
                patch("pathlib.Path", path_cls),
            )
        )
        try:
            await org_template_edit_page(
                _request(), str(tenant.id), _customizable(), AsyncMock(), AsyncMock()
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["default_content"] == ""
        assert ctx["template"] is None


class TestOrgTemplateEditSubmit:
    async def test_non_customizable_template_is_rejected(self):
        from auth.api.routes.auth.settings import org_template_edit_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_template_edit_submit(
                _request(form_data={}),
                str(tenant.id),
                "secret/internal.html",
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Template+is+not+customizable" in result.headers["location"]

    async def test_empty_content_is_rejected(self):
        from auth.api.routes.auth.settings import org_template_edit_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_template_edit_submit(
                _request(form_data={"content": "  "}),
                str(tenant.id),
                _customizable(),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Content+is+required" in result.headers["location"]

    async def test_invalid_jinja_syntax_is_rejected(self):
        from auth.api.routes.auth.settings import org_template_edit_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_template_edit_submit(
                _request(form_data={"content": "{% if %}"}),
                str(tenant.id),
                _customizable(),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Invalid+Jinja2+syntax" in result.headers["location"]

    async def test_invalid_mjml_syntax_is_rejected(self):
        from auth.api.routes.auth.settings import org_template_edit_submit

        tenant = _tenant()
        name = _customizable_mjml()

        with (
            _authorised(tenant),
            patch.dict(
                "sys.modules",
                {"mrml": MagicMock(to_html=MagicMock(side_effect=ValueError("bad mjml")))},
            ),
        ):
            result = await org_template_edit_submit(
                _request(form_data={"content": "<mjml>"}),
                str(tenant.id),
                name,
                AsyncMock(),
                AsyncMock(),
            )

        assert "Invalid+MJML+syntax" in result.headers["location"]

    async def test_valid_html_template_is_saved(self):
        from auth.api.routes.auth.settings import org_template_edit_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.upsert_template", AsyncMock()) as upsert,
        ):
            result = await org_template_edit_submit(
                _request(
                    form_data={
                        "content": "<p>{{ name }}</p>",
                        "description": "Login",
                        "is_active": "true",
                    }
                ),
                str(tenant.id),
                _customizable(),
                AsyncMock(),
                AsyncMock(),
            )

        assert upsert.await_args.kwargs["is_active"] is True
        assert "success=Template+saved" in result.headers["location"]

    async def test_mjml_save_invalidates_the_renderer_cache(self):
        from auth.api.routes.auth.settings import org_template_edit_submit

        tenant = _tenant()
        renderer = MagicMock()

        with (
            _authorised(tenant),
            patch.dict("sys.modules", {"mrml": MagicMock(to_html=MagicMock())}),
            patch(f"{MODULE}.tenant_service.upsert_template", AsyncMock()),
            patch("auth.services.email_renderer.get_email_renderer", return_value=renderer),
        ):
            result = await org_template_edit_submit(
                _request(form_data={"content": "<mjml></mjml>"}),
                str(tenant.id),
                _customizable_mjml(),
                AsyncMock(),
                AsyncMock(),
            )

        renderer.invalidate_tenant_cache.assert_called_once()
        assert "success=Template+saved" in result.headers["location"]

    async def test_save_failure_is_reported(self):
        from auth.api.routes.auth.settings import org_template_edit_submit

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.upsert_template",
                AsyncMock(side_effect=RuntimeError("db down")),
            ),
        ):
            result = await org_template_edit_submit(
                _request(form_data={"content": "<p>ok</p>"}),
                str(tenant.id),
                _customizable(),
                AsyncMock(),
                AsyncMock(),
            )

        assert "db+down" in result.headers["location"]


class TestOrgTemplateDeleteAndToggle:
    async def test_existing_override_is_deleted(self):
        from auth.api.routes.auth.settings import org_template_delete

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_template",
                AsyncMock(return_value=_template_row()),
            ),
            patch(f"{MODULE}.tenant_service.delete_template", AsyncMock()) as delete,
        ):
            result = await org_template_delete(
                _request(), str(tenant.id), _customizable(), AsyncMock(), AsyncMock()
            )

        delete.assert_awaited_once()
        assert "success=Template+deleted" in result.headers["location"]

    async def test_absent_override_delete_is_a_no_op(self):
        from auth.api.routes.auth.settings import org_template_delete

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_template", AsyncMock(return_value=None)),
            patch(f"{MODULE}.tenant_service.delete_template", AsyncMock()) as delete,
        ):
            result = await org_template_delete(
                _request(), str(tenant.id), _customizable(), AsyncMock(), AsyncMock()
            )

        delete.assert_not_awaited()
        assert result.status_code == 303

    async def test_missing_override_toggle_is_reported(self):
        from auth.api.routes.auth.settings import org_template_toggle

        tenant = _tenant()

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_template", AsyncMock(return_value=None)),
        ):
            result = await org_template_toggle(
                _request(), str(tenant.id), _customizable(), AsyncMock(), AsyncMock()
            )

        assert "error=Template+not+found" in result.headers["location"]

    @pytest.mark.parametrize(("is_active", "word"), [(True, "enabled"), (False, "disabled")])
    async def test_toggle_reports_the_new_state(self, is_active, word):
        from auth.api.routes.auth.settings import org_template_toggle

        tenant = _tenant()
        row = _template_row(is_active=is_active)

        with (
            _authorised(tenant),
            patch(f"{MODULE}.tenant_service.get_template", AsyncMock(return_value=row)),
            patch(f"{MODULE}.tenant_service.toggle_template", AsyncMock()) as toggle,
        ):
            result = await org_template_toggle(
                _request(), str(tenant.id), _customizable(), AsyncMock(), AsyncMock()
            )

        toggle.assert_awaited_once()
        assert f"success=Template+{word}" in result.headers["location"]


# ---------------------------------------------------------------------------
# Trust policy
# ---------------------------------------------------------------------------


class TestOrgTrustPage:
    async def test_missing_config_falls_back_to_none(self):
        from auth.api.routes.auth.settings import org_trust_page

        tenant = _tenant()
        templates, page_patches = _patch_page()
        trust_service = AsyncMock()
        trust_service.get_tenant_trust_config = AsyncMock(return_value=None)
        trust_service.get_available_tenants_for_trust = AsyncMock(return_value=[])

        _entered, close = _enter((*page_patches, _authorised(tenant)))
        try:
            await org_trust_page(
                _request(), str(tenant.id), AsyncMock(), AsyncMock(), trust_service
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["trust_mode"] == "none"
        assert ctx["trusted_sources"] == []

    async def test_existing_config_is_rendered(self):
        from auth.api.routes.auth.settings import org_trust_page

        tenant = _tenant()
        templates, page_patches = _patch_page()
        trust_service = AsyncMock()
        trust_service.get_tenant_trust_config = AsyncMock(
            return_value={"trust_mode": "all", "trusted_sources": [{"id": "s"}]}
        )
        trust_service.get_available_tenants_for_trust = AsyncMock(return_value=[])

        _entered, close = _enter((*page_patches, _authorised(tenant)))
        try:
            await org_trust_page(
                _request(), str(tenant.id), AsyncMock(), AsyncMock(), trust_service
            )
        finally:
            close()

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["trust_mode"] == "all"
        assert ctx["trusted_sources"] == [{"id": "s"}]


class TestOrgTrustSubmits:
    async def test_unknown_mode_is_rejected(self):
        from auth.api.routes.auth.settings import org_trust_mode_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_trust_mode_submit(
                _request(form_data={"trust_mode": "wide-open"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Invalid+trust+mode" in result.headers["location"]

    async def test_valid_mode_is_applied(self):
        from auth.api.routes.auth.settings import org_trust_mode_submit
        from auth.db.models.tenant import TenantTrustMode

        tenant = _tenant()
        trust_service = AsyncMock()

        with _authorised(tenant):
            result = await org_trust_mode_submit(
                _request(form_data={"trust_mode": TenantTrustMode.ALL.value}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
                trust_service,
            )

        trust_service.update_trust_mode.assert_awaited_once()
        assert "success=Trust+mode+updated" in result.headers["location"]

    async def test_add_source_requires_a_selection(self):
        from auth.api.routes.auth.settings import org_trust_add_source_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_trust_add_source_submit(
                _request(form_data={}), str(tenant.id), AsyncMock(), AsyncMock(), AsyncMock()
            )

        assert "error=Please+select+an+organization" in result.headers["location"]

    async def test_add_source_rejects_an_unparseable_id(self):
        from auth.api.routes.auth.settings import org_trust_add_source_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_trust_add_source_submit(
                _request(form_data={"trusted_tenant_id": "not-a-uuid"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Invalid+organization+ID" in result.headers["location"]

    async def test_add_source_reports_a_duplicate(self):
        from auth.api.routes.auth.settings import org_trust_add_source_submit

        tenant = _tenant()
        trust_service = AsyncMock()
        trust_service.add_trusted_source = AsyncMock(return_value=None)

        with _authorised(tenant):
            result = await org_trust_add_source_submit(
                _request(form_data={"trusted_tenant_id": str(uuid.uuid4())}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
                trust_service,
            )

        assert "already+trusted" in result.headers["location"]

    async def test_add_source_succeeds(self):
        from auth.api.routes.auth.settings import org_trust_add_source_submit

        tenant = _tenant()
        trust_service = AsyncMock()
        trust_service.add_trusted_source = AsyncMock(return_value=MagicMock())

        with _authorised(tenant):
            result = await org_trust_add_source_submit(
                _request(
                    form_data={
                        "trusted_tenant_id": str(uuid.uuid4()),
                        "description": " partner ",
                    }
                ),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
                trust_service,
            )

        assert trust_service.add_trusted_source.await_args[0][3] == "partner"
        assert "success=Trusted+source+added" in result.headers["location"]

    async def test_remove_source_rejects_an_unparseable_id(self):
        from auth.api.routes.auth.settings import org_trust_remove_source_submit

        tenant = _tenant()

        with _authorised(tenant):
            result = await org_trust_remove_source_submit(
                _request(), str(tenant.id), "not-a-uuid", AsyncMock(), AsyncMock(), AsyncMock()
            )

        assert "error=Invalid+source+ID" in result.headers["location"]

    async def test_remove_source_reports_a_miss(self):
        from auth.api.routes.auth.settings import org_trust_remove_source_submit

        tenant = _tenant()
        trust_service = AsyncMock()
        trust_service.remove_trusted_source = AsyncMock(return_value=False)

        with _authorised(tenant):
            result = await org_trust_remove_source_submit(
                _request(),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
                trust_service,
            )

        assert "error=Trusted+source+not+found" in result.headers["location"]

    async def test_remove_source_succeeds(self):
        from auth.api.routes.auth.settings import org_trust_remove_source_submit

        tenant = _tenant()
        trust_service = AsyncMock()
        trust_service.remove_trusted_source = AsyncMock(return_value=True)

        with _authorised(tenant):
            result = await org_trust_remove_source_submit(
                _request(),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
                trust_service,
            )

        assert "success=Trusted+source+removed" in result.headers["location"]


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def _webhook(tenant_id=None, is_active=True):
    webhook = MagicMock()
    webhook.id = uuid.uuid4()
    webhook.tenant_id = tenant_id or uuid.uuid4()
    webhook.name = "Hook"
    webhook.url = "https://hooks.example.com/a"
    webhook.events = ["*"]
    webhook.is_active = is_active
    webhook.secret = "old-secret"
    return webhook


class TestDispatchTenantEvent:
    async def test_dispatch_failures_are_swallowed(self):
        from auth.api.routes.auth.settings import _dispatch_tenant_event
        from auth.db.models.tenant import WebhookEvent

        with patch(
            f"{MODULE}.webhook_service.dispatch",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await _dispatch_tenant_event(
                AsyncMock(),
                tenant_id=uuid.uuid4(),
                event=WebhookEvent.TENANT_UPDATED,
                data={},
            )


class TestSanitizeEvents:
    def test_blanks_and_duplicates_are_dropped(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["", "  ", "*", "*"]) == ["*"]

    def test_known_event_is_kept(self):
        from auth.api.routes.auth.settings import _sanitize_events
        from auth.db.models.tenant import WebhookEvent

        value = next(iter(WebhookEvent)).value

        assert _sanitize_events([value]) == [value]

    def test_group_wildcard_is_kept(self):
        from auth.api.routes.auth.settings import _sanitize_events
        from auth.db.models.tenant import WebhookEvent

        prefix = next(iter(WebhookEvent)).value.split(".", 1)[0]

        assert _sanitize_events([f"{prefix}.*"]) == [f"{prefix}.*"]

    def test_unknown_values_are_dropped(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["nosuchgroup.*", "not-an-event"]) == []


class TestGetTenantWebhook:
    async def test_unparseable_id_returns_none(self):
        from auth.api.routes.auth.settings import _get_tenant_webhook

        assert await _get_tenant_webhook(AsyncMock(), uuid.uuid4(), "not-a-uuid") is None

    async def test_delegates_to_the_service(self):
        from auth.api.routes.auth.settings import _get_tenant_webhook

        webhook = _webhook()

        with patch(f"{MODULE}.webhook_service.get_for_tenant", AsyncMock(return_value=webhook)):
            result = await _get_tenant_webhook(AsyncMock(), uuid.uuid4(), str(webhook.id))

        assert result is webhook


class TestLoadTenantWebhooks:
    async def test_each_webhook_gets_its_recent_deliveries(self):
        from auth.api.routes.auth.settings import _load_tenant_webhooks

        webhook = _webhook()

        with (
            patch(
                f"{MODULE}.webhook_service.list_all_for_tenant",
                AsyncMock(return_value=[webhook]),
            ),
            patch(
                f"{MODULE}.webhook_service.list_recent_deliveries",
                AsyncMock(return_value=[]),
            ) as recent,
        ):
            result = await _load_tenant_webhooks(AsyncMock(), webhook.tenant_id)

        recent.assert_awaited_once()
        assert result[0]["id"] == str(webhook.id)


def _valid_event():
    from auth.db.models.tenant import WebhookEvent

    return next(iter(WebhookEvent)).value


class TestOrgWebhookCreate:
    async def test_name_is_required(self):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_webhook_create_submit(
                _request(form_data={}), str(tenant.id), AsyncMock(), AsyncMock()
            )

        assert "error=Webhook+name+is+required" in result.headers["location"]

    async def test_overlong_name_is_rejected(self):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_webhook_create_submit(
                _request(form_data={"name": "a" * 101}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "100+characters" in result.headers["location"]

    async def test_url_is_required(self):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_webhook_create_submit(
                _request(form_data={"name": "Hook"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Webhook+URL+is+required" in result.headers["location"]

    async def test_at_least_one_event_is_required(self):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = _tenant()

        with _authorised_manager(tenant):
            result = await org_webhook_create_submit(
                _request(form_data={"name": "Hook", "url": "https://hooks.example.com/a"}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "at+least+one+event" in result.headers["location"]

    async def test_unsafe_url_is_rejected(self):
        from auth.api.routes.auth.settings import org_webhook_create_submit
        from auth.services.webhook import WebhookURLError

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}.webhook_validate_target_url",
                side_effect=WebhookURLError("private address"),
            ),
        ):
            result = await org_webhook_create_submit(
                _request(
                    form_data={
                        "name": "Hook",
                        "url": "http://127.0.0.1/hook",
                        "events": [_valid_event()],
                    }
                ),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Invalid+webhook+URL" in result.headers["location"]

    async def test_webhook_is_created_with_a_one_shot_secret(self):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = _tenant()
        webhook = _webhook(tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}.webhook_validate_target_url"),
            patch(f"{MODULE}.webhook_generate_secret", return_value="whsec"),
            patch(
                f"{MODULE}.webhook_service.create_for_tenant",
                AsyncMock(return_value=webhook),
            ) as create,
        ):
            result = await org_webhook_create_submit(
                _request(
                    form_data={
                        "name": "Hook",
                        "url": "https://hooks.example.com/a",
                        "events": [_valid_event()],
                    }
                ),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        create.assert_awaited_once()
        assert "new_webhook_secret=whsec" in result.headers["location"]


class TestOrgWebhookUpdate:
    async def test_missing_webhook_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_update_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=None)),
        ):
            result = await org_webhook_update_submit(
                _request(form_data={}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Webhook+not+found" in result.headers["location"]

    @pytest.mark.parametrize("name", ["", "a" * 101])
    async def test_invalid_name_is_rejected(self, name):
        from auth.api.routes.auth.settings import org_webhook_update_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=_webhook(tenant.id))),
        ):
            result = await org_webhook_update_submit(
                _request(form_data={"name": name}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Invalid+webhook+name" in result.headers["location"]

    async def test_url_is_required(self):
        from auth.api.routes.auth.settings import org_webhook_update_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=_webhook(tenant.id))),
        ):
            result = await org_webhook_update_submit(
                _request(form_data={"name": "Hook"}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Webhook+URL+is+required" in result.headers["location"]

    async def test_at_least_one_event_is_required(self):
        from auth.api.routes.auth.settings import org_webhook_update_submit

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=_webhook(tenant.id))),
        ):
            result = await org_webhook_update_submit(
                _request(form_data={"name": "Hook", "url": "https://hooks.example.com/a"}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Select+at+least+one+event" in result.headers["location"]

    async def test_unsafe_url_is_rejected(self):
        from auth.api.routes.auth.settings import org_webhook_update_submit
        from auth.services.webhook import WebhookURLError

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=_webhook(tenant.id))),
            patch(
                f"{MODULE}.webhook_validate_target_url",
                side_effect=WebhookURLError("private address"),
            ),
        ):
            result = await org_webhook_update_submit(
                _request(
                    form_data={
                        "name": "Hook",
                        "url": "http://127.0.0.1/hook",
                        "events": [_valid_event()],
                    }
                ),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "Invalid+webhook+URL" in result.headers["location"]

    async def test_webhook_is_updated(self):
        from auth.api.routes.auth.settings import org_webhook_update_submit

        tenant = _tenant()
        webhook = _webhook(tenant.id)
        event = _valid_event()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=webhook)),
            patch(f"{MODULE}.webhook_validate_target_url"),
        ):
            result = await org_webhook_update_submit(
                _request(
                    form_data={
                        "name": "Renamed",
                        "url": "https://hooks.example.com/v2",
                        "events": [event],
                    }
                ),
                str(tenant.id),
                str(webhook.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert webhook.name == "Renamed"
        assert webhook.url == "https://hooks.example.com/v2"
        assert webhook.events == [event]
        assert "success=Webhook+updated" in result.headers["location"]


class TestOrgWebhookLifecycle:
    @pytest.mark.parametrize(("initial", "word"), [(True, "paused"), (False, "resumed")])
    async def test_toggle_reports_the_new_state(self, initial, word):
        from auth.api.routes.auth.settings import org_webhook_toggle

        tenant = _tenant()
        webhook = _webhook(tenant.id, is_active=initial)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=webhook)),
        ):
            result = await org_webhook_toggle(
                _request(), str(tenant.id), str(webhook.id), AsyncMock(), AsyncMock()
            )

        assert webhook.is_active is not initial
        assert f"success=Webhook+{word}" in result.headers["location"]

    async def test_toggle_missing_webhook_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_toggle

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=None)),
        ):
            result = await org_webhook_toggle(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Webhook+not+found" in result.headers["location"]

    async def test_rotate_secret(self):
        from auth.api.routes.auth.settings import org_webhook_rotate_secret

        tenant = _tenant()
        webhook = _webhook(tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=webhook)),
            patch(f"{MODULE}.webhook_generate_secret", return_value="whsec2"),
        ):
            result = await org_webhook_rotate_secret(
                _request(), str(tenant.id), str(webhook.id), AsyncMock(), AsyncMock()
            )

        assert webhook.secret == "whsec2"
        assert "new_webhook_secret=whsec2" in result.headers["location"]

    async def test_rotate_secret_missing_webhook_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_rotate_secret

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=None)),
        ):
            result = await org_webhook_rotate_secret(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Webhook+not+found" in result.headers["location"]

    async def test_test_delivery_missing_webhook_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_test

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=None)),
        ):
            result = await org_webhook_test(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Webhook+not+found" in result.headers["location"]

    async def test_test_delivery_rejects_an_unsafe_url(self):
        from auth.api.routes.auth.settings import org_webhook_test
        from auth.services.webhook import WebhookURLError

        tenant = _tenant()
        webhook = _webhook(tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=webhook)),
            patch(
                f"{MODULE}.webhook_validate_target_url",
                side_effect=WebhookURLError("private address"),
            ),
        ):
            result = await org_webhook_test(
                _request(), str(tenant.id), str(webhook.id), AsyncMock(), AsyncMock()
            )

        assert "Cannot+test" in result.headers["location"]

    async def test_test_delivery_is_created(self):
        from auth.api.routes.auth.settings import org_webhook_test

        tenant = _tenant()
        webhook = _webhook(tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=webhook)),
            patch(f"{MODULE}.webhook_validate_target_url"),
            patch(f"{MODULE}.webhook_service.create_test_delivery", AsyncMock()) as create_test,
        ):
            result = await org_webhook_test(
                _request(), str(tenant.id), str(webhook.id), AsyncMock(), AsyncMock()
            )

        create_test.assert_awaited_once()
        assert "success=Test+delivery+sent" in result.headers["location"]

    async def test_delete_missing_webhook_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_delete

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=None)),
        ):
            result = await org_webhook_delete(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        assert "error=Webhook+not+found" in result.headers["location"]

    async def test_delete(self):
        from auth.api.routes.auth.settings import org_webhook_delete

        tenant = _tenant()
        webhook = _webhook(tenant.id)

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=webhook)),
            patch(f"{MODULE}.webhook_service.delete", AsyncMock()) as delete,
        ):
            result = await org_webhook_delete(
                _request(), str(tenant.id), str(webhook.id), AsyncMock(), AsyncMock()
            )

        delete.assert_awaited_once()
        assert "success=Webhook+deleted" in result.headers["location"]


class TestOrgWebhookReplay:
    async def test_missing_webhook_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_replay_delivery

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=None)),
        ):
            result = await org_webhook_replay_delivery(
                _request(),
                str(tenant.id),
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Webhook+not+found" in result.headers["location"]

    async def test_unparseable_delivery_id_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_replay_delivery

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=_webhook(tenant.id))),
        ):
            result = await org_webhook_replay_delivery(
                _request(),
                str(tenant.id),
                str(uuid.uuid4()),
                "not-a-uuid",
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Invalid+delivery+id" in result.headers["location"]

    async def test_missing_delivery_is_reported(self):
        from auth.api.routes.auth.settings import org_webhook_replay_delivery

        tenant = _tenant()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=_webhook(tenant.id))),
            patch(
                f"{MODULE}.webhook_service.get_delivery_for_webhook",
                AsyncMock(return_value=None),
            ),
        ):
            result = await org_webhook_replay_delivery(
                _request(),
                str(tenant.id),
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert "error=Delivery+not+found" in result.headers["location"]

    async def test_delivery_is_replayed(self):
        from auth.api.routes.auth.settings import org_webhook_replay_delivery

        tenant = _tenant()
        webhook = _webhook(tenant.id)
        replay = MagicMock()
        replay.id = uuid.uuid4()

        with (
            _authorised_manager(tenant),
            patch(f"{MODULE}._get_tenant_webhook", AsyncMock(return_value=webhook)),
            patch(
                f"{MODULE}.webhook_service.get_delivery_for_webhook",
                AsyncMock(return_value=MagicMock()),
            ),
            patch(
                f"{MODULE}.webhook_service.replay_delivery", AsyncMock(return_value=replay)
            ) as replay_call,
        ):
            result = await org_webhook_replay_delivery(
                _request(),
                str(tenant.id),
                str(webhook.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        replay_call.assert_awaited_once()
        assert "success=Delivery+replayed" in result.headers["location"]


# ---------------------------------------------------------------------------
# Remaining branches
# ---------------------------------------------------------------------------


class TestSecurityPageBackupCodes:
    async def test_missing_backup_code_status_leaves_the_counts_unset(self):
        from auth.api.routes.auth.settings import settings_security

        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_service.get_backup_codes_status = AsyncMock(return_value=None)

        branding_service = AsyncMock()
        branding_service.render_template = AsyncMock(return_value="<html>ok</html>")

        session_service = AsyncMock()
        session_service.get_user_by_session_token = AsyncMock(return_value=_user())

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(f"{MODULE}.check_user_is_admin", AsyncMock(return_value=(False, {}))),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            result = await settings_security(
                _request(), AsyncMock(), session_service, mfa_service, branding_service
            )

        assert result.status_code == 200
        ctx = branding_service.render_template.await_args[0][2]
        assert ctx["backup_codes_remaining"] is None


class TestSettingsTenantsPage:
    def _membership(self, tenant=None, role_name="member"):
        membership = MagicMock()
        membership.id = uuid.uuid4()
        membership.tenant = tenant
        membership.role_name = role_name
        membership.role_display_name = role_name.capitalize()
        membership.joined_at = _now()
        membership.created_at = _now()
        return membership

    def _fed(self, idp=None, email="ext@example.com"):
        fed = MagicMock()
        fed.identity_provider = idp
        fed.external_email = email
        fed.last_login_at = _now()
        return fed

    async def _run(self, memberships, federated):
        from auth.api.routes.auth.settings import settings_tenants

        branding_service = AsyncMock()
        branding_service.render_template = AsyncMock(return_value="<html>ok</html>")
        session_service = AsyncMock()
        session_service.get_user_by_session_token = AsyncMock(return_value=_user())

        with (
            patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
            patch(
                f"{MODULE}.tenant_service.list_user_memberships_with_idps",
                AsyncMock(return_value=memberships),
            ),
            patch(
                f"{MODULE}.federation_service.list_user_federated_identities",
                AsyncMock(return_value=federated),
            ),
            patch(f"{MODULE}.check_user_is_admin", AsyncMock(return_value=(False, {}))),
            patch(f"{MODULE}.get_tenant_prefix", return_value=""),
            patch(f"{MODULE}.get_current_tenant_id", return_value=None),
        ):
            await settings_tenants(_request(), AsyncMock(), session_service, branding_service)

        return branding_service.render_template.await_args[0][2]

    async def test_memberships_without_a_tenant_are_skipped(self):
        ctx = await self._run([self._membership(tenant=None)], [])

        assert ctx["memberships"] == []

    async def test_linked_and_available_idps_are_split(self):
        tenant = _tenant()
        linked_idp = _idp(tenant.id)
        spare_idp = _idp(tenant.id)
        foreign_idp = _idp(uuid.uuid4())
        tenant.identity_providers = [linked_idp, spare_idp]

        ctx = await self._run(
            [self._membership(tenant=tenant)],
            [self._fed(linked_idp), self._fed(foreign_idp), self._fed(None)],
        )

        entry = ctx["memberships"][0]
        assert [i["id"] for i in entry["linked_idps"]] == [str(linked_idp.id)]
        assert [i["id"] for i in entry["available_idps"]] == [str(spare_idp.id)]

    async def test_join_date_falls_back_to_created_at(self):
        tenant = _tenant()
        membership = self._membership(tenant=tenant)
        membership.joined_at = None

        ctx = await self._run([membership], [])

        assert ctx["memberships"][0]["joined_at"] == membership.created_at.isoformat()

    async def test_membership_without_any_date(self):
        tenant = _tenant()
        membership = self._membership(tenant=tenant)
        membership.joined_at = None
        membership.created_at = None

        ctx = await self._run([membership], [])

        assert ctx["memberships"][0]["joined_at"] is None


class TestLeaveTenantStaleSession:
    async def test_stale_session_redirects_to_login(self):
        from auth.api.routes.auth.settings import settings_leave_tenant

        session_service = AsyncMock()
        session_service.get_user_by_session_token = AsyncMock(return_value=None)

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_leave_tenant(
                _request(), str(uuid.uuid4()), AsyncMock(), session_service
            )

        assert "/auth/login" in result.headers["location"]


class TestGetAllAvailableScopes:
    async def test_without_a_tenant_the_full_catalogue_is_returned(self):
        from auth.api.routes.auth.settings import TENANT_SCOPES, get_all_available_scopes

        with patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[_scope()])):
            result = await get_all_available_scopes(AsyncMock())

        assert result["tenant"] == TENANT_SCOPES
        assert result["application"] == {"members:read": "desc"}

    async def test_scope_without_a_description_falls_back_to_its_name(self):
        from auth.api.routes.auth.settings import get_all_available_scopes

        scope = _scope()
        scope.description = None

        with patch(f"{MODULE}.scope_service.list_active", AsyncMock(return_value=[scope])):
            result = await get_all_available_scopes(AsyncMock(), tenant=_tenant())

        assert result["application"] == {"members:read": "members:read"}


class TestTrustSourceToDict:
    def test_resolved_source_tenant(self):
        from auth.api.routes.auth.settings import trust_source_to_dict

        source = MagicMock()
        source.id = uuid.uuid4()
        source.trusted_tenant_id = uuid.uuid4()
        source.trusted_tenant = MagicMock()
        source.trusted_tenant.display_name = "Partner"
        source.trusted_tenant.slug = "partner"
        source.description = "Partner org"
        source.created_at = _now()

        result = trust_source_to_dict(source)

        assert result["trusted_tenant_name"] == "Partner"
        assert result["trusted_tenant_slug"] == "partner"

    def test_platform_source_falls_back_to_main_domain(self):
        from auth.api.routes.auth.settings import trust_source_to_dict

        source = MagicMock()
        source.id = uuid.uuid4()
        source.trusted_tenant_id = None
        source.trusted_tenant = None
        source.description = None
        source.created_at = None

        result = trust_source_to_dict(source)

        assert result["trusted_tenant_id"] is None
        assert result["trusted_tenant_name"] == "Main Domain"
        assert result["trusted_tenant_slug"] is None
        assert result["created_at"] is None


class TestOrgDomainSubmitBlankStoredDomain:
    async def test_clearing_an_empty_stored_domain_triggers_no_task(self):
        """A tenant whose stored domain is the empty string clears without a task."""
        from auth.api.routes.auth.settings import org_domain_submit

        tenant = _tenant()
        tenant.custom_domain = ""
        module = MagicMock()

        with (
            _authorised(tenant),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
            patch.dict("sys.modules", {"auth.tasks.custom_domain": module}),
        ):
            result = await org_domain_submit(
                _request(form_data={"custom_domain": ""}),
                str(tenant.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert tenant.custom_domain is None
        module.verify_custom_domain_dns.delay.assert_not_called()
        module.remove_custom_domain_config.delay.assert_not_called()
        assert "success=Custom+domain+updated" in result.headers["location"]


class TestOrgMemberOwnershipEdgeCases:
    async def test_non_owner_may_change_a_non_owner_member(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()
        actor = _member(tenant.id, scopes=("members:write",))
        target = _member(tenant.id, scopes=("members:read",))
        new_role = _role(name="viewer", tenant_id=tenant.id)

        with (
            _authorised(tenant, actor),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=target),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=new_role),
            ),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role_id": str(uuid.uuid4())}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert target.role_id == new_role.id
        assert "success=Member+role+updated" in result.headers["location"]

    async def test_an_owner_may_be_demoted_when_another_owner_remains(self):
        from auth.api.routes.auth.settings import org_update_member_role_submit

        tenant = _tenant()
        target = _member(tenant.id, scopes=("*",))
        co_owner = _member(tenant.id, scopes=("*",))
        new_role = _role(name="member", tenant_id=tenant.id)

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=target),
            ),
            patch(
                f"{MODULE}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=new_role),
            ),
            patch(
                f"{MODULE}.tenant_service.list_members",
                AsyncMock(return_value=[target, co_owner]),
            ),
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_update_member_role_submit(
                _request(form_data={"role_id": str(uuid.uuid4())}),
                str(tenant.id),
                str(uuid.uuid4()),
                AsyncMock(),
                AsyncMock(),
            )

        assert target.role_id == new_role.id
        assert "success=Member+role+updated" in result.headers["location"]

    async def test_an_owner_may_be_removed_when_another_owner_remains(self):
        from auth.api.routes.auth.settings import org_remove_member_submit

        tenant = _tenant()
        target = _member(tenant.id, scopes=("*",))
        co_owner = _member(tenant.id, scopes=("*",))

        with (
            _authorised(tenant),
            patch(
                f"{MODULE}.tenant_service.get_member_in_tenant",
                AsyncMock(return_value=target),
            ),
            patch(
                f"{MODULE}.tenant_service.list_members",
                AsyncMock(return_value=[target, co_owner]),
            ),
            patch(f"{MODULE}.tenant_service.remove_member", AsyncMock()) as remove,
            patch(f"{MODULE}._dispatch_tenant_event", AsyncMock()),
        ):
            result = await org_remove_member_submit(
                _request(), str(tenant.id), str(uuid.uuid4()), AsyncMock(), AsyncMock()
            )

        remove.assert_awaited_once()
        assert "success=Member+removed" in result.headers["location"]


class TestOrgClientEditSubmitTypeUnchanged:
    async def test_public_client_stays_public_without_a_new_secret(self):
        from auth.api.routes.auth.settings import org_client_edit_submit

        tenant = _tenant()
        client = _client(tenant.id, is_confidential=False)
        client.client_secret_hash = None

        with (
            _authorised_manager(tenant),
            patch(
                f"{MODULE}._oauth2_client_service.get_scoped_to_tenant",
                AsyncMock(return_value=client),
            ),
        ):
            result = await org_client_edit_submit(
                _request(form_data={"name": "My App"}),
                str(tenant.id),
                str(client.id),
                AsyncMock(),
                AsyncMock(),
            )

        assert client.is_confidential is False
        assert client.client_secret_hash is None
        assert "new_secret=" not in result.headers["location"]
