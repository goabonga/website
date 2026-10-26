# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the tenant settings sub-pages of auth.api.routes.admin.tenants_pages.

Covers the registration/profile field editors, email sender, allowed scopes,
branding, templates, trust policy and custom-role management handlers.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_user

TENANTS_PAGES = "auth.api.routes.admin.tenants_pages"

pytestmark = pytest.mark.asyncio


def _now():
    return datetime.now(UTC)


def _auth():
    return (make_user(), [MagicMock()])


def _templates():
    templates = MagicMock()
    templates.TemplateResponse.return_value = MagicMock()
    return templates


def _form(data):
    """Build a mock starlette FormData."""
    form = MagicMock()
    form.get = lambda key, default="": data.get(key, default)
    form.items = lambda: data.items()
    form.getlist = lambda key: data.get(key, [])
    return form


def _request(query_params=None, form_data=None):
    request = MagicMock()
    request.query_params = query_params or {}
    request.form = AsyncMock(return_value=_form(form_data or {}))
    return request


def _tenant(settings=None, branding=None, templates_list=None):
    tenant = MagicMock()
    tenant.id = uuid.uuid4()
    tenant.slug = "acme"
    tenant.display_name = "Acme Corp"
    tenant.custom_domain = None
    tenant.is_active = True
    tenant.is_platform = False
    tenant.settings = settings if settings is not None else {}
    tenant.members = []
    tenant.identity_providers = []
    tenant.roles = []
    tenant.branding = branding
    tenant.templates = templates_list or []
    tenant.created_at = _now()
    tenant.updated_at = _now()
    return tenant


def _patch_resolve(tenant, name="resolve"):
    return patch(f"{TENANTS_PAGES}._tenant_service.{name}", AsyncMock(return_value=tenant))


def _patch_page(templates):
    return (
        patch(f"{TENANTS_PAGES}.get_templates", return_value=templates),
        patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={"can": True}),
    )


# ---------------------------------------------------------------------------
# Registration fields
# ---------------------------------------------------------------------------


class TestRegistrationFieldsPage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_registration_fields_page

        tpl, perms = _patch_page(_templates())
        with tpl, perms, _patch_resolve(None), pytest.raises(HTTPException) as exc:
            await tenant_registration_fields_page(_request(), "acme", AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_defaults_are_all_enabled(self):
        from auth.api.routes.admin.tenants_pages import (
            _REGISTRATION_FIELD_KEYS,
            tenant_registration_fields_page,
        )

        templates = _templates()
        tpl, perms = _patch_page(templates)
        with tpl, perms, _patch_resolve(_tenant()):
            await tenant_registration_fields_page(_request(), "acme", AsyncMock(), _auth())

        fields = templates.TemplateResponse.call_args.kwargs["context"]["fields"]
        assert fields == dict.fromkeys(_REGISTRATION_FIELD_KEYS, True)

    async def test_overrides_are_applied(self):
        from auth.api.routes.admin.tenants_pages import (
            _REGISTRATION_FIELD_KEYS,
            tenant_registration_fields_page,
        )

        key = _REGISTRATION_FIELD_KEYS[0]
        tenant = _tenant(settings={"registration_fields": {key: False}})
        templates = _templates()
        tpl, perms = _patch_page(templates)
        with tpl, perms, _patch_resolve(tenant):
            await tenant_registration_fields_page(_request(), "acme", AsyncMock(), _auth())

        fields = templates.TemplateResponse.call_args.kwargs["context"]["fields"]
        assert fields[key] is False


class TestRegistrationFieldsSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_registration_fields_submit

        with _patch_resolve(None):
            result = await tenant_registration_fields_submit(
                _request(form_data={}), "acme", AsyncMock(), _auth()
            )

        assert result.status_code == 303
        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_checked_fields_are_persisted(self):
        from auth.api.routes.admin.tenants_pages import (
            _REGISTRATION_FIELD_KEYS,
            tenant_registration_fields_submit,
        )

        tenant = _tenant()
        enabled = _REGISTRATION_FIELD_KEYS[0]
        db = AsyncMock()

        with _patch_resolve(tenant):
            result = await tenant_registration_fields_submit(
                _request(form_data={enabled: "true"}), "acme", db, _auth()
            )

        assert result.status_code == 303
        assert "success=Registration+fields+updated" in result.headers["location"]
        stored = tenant.settings["registration_fields"]
        assert stored[enabled] is True
        assert all(v is False for k, v in stored.items() if k != enabled)
        db.commit.assert_awaited_once()

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_registration_fields_submit

        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with _patch_resolve(_tenant()):
            result = await tenant_registration_fields_submit(
                _request(form_data={}), "acme", db, _auth()
            )

        assert "error=db%20down" in result.headers["location"]


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------


class TestEmailSenderSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_email_sender_submit

        with _patch_resolve(None):
            result = await tenant_email_sender_submit(
                _request(form_data={}), "acme", AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_values_are_stored_and_the_worker_cache_is_invalidated(self):
        from auth.api.routes.admin.tenants_pages import tenant_email_sender_submit

        tenant = _tenant()
        db = AsyncMock()
        form = {"email_sender_address": " noreply@acme.test ", "email_sender_name": " Acme "}

        with (
            _patch_resolve(tenant),
            patch("auth.tasks.email.invalidate_platform_sender_cache") as invalidate,
        ):
            result = await tenant_email_sender_submit(_request(form_data=form), "acme", db, _auth())

        assert "success=Email+sender+updated" in result.headers["location"]
        assert tenant.settings["email_sender_address"] == "noreply@acme.test"
        assert tenant.settings["email_sender_name"] == "Acme"
        invalidate.assert_called_once()

    async def test_blank_values_become_null(self):
        from auth.api.routes.admin.tenants_pages import tenant_email_sender_submit

        tenant = _tenant()

        with (
            _patch_resolve(tenant),
            patch("auth.tasks.email.invalidate_platform_sender_cache"),
        ):
            await tenant_email_sender_submit(
                _request(form_data={"email_sender_address": "   "}), "acme", AsyncMock(), _auth()
            )

        assert tenant.settings["email_sender_address"] is None
        assert tenant.settings["email_sender_name"] is None

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_email_sender_submit

        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with _patch_resolve(_tenant()):
            result = await tenant_email_sender_submit(_request(form_data={}), "acme", db, _auth())

        assert "error=db%20down" in result.headers["location"]


# ---------------------------------------------------------------------------
# Profile fields
# ---------------------------------------------------------------------------


class TestProfileFieldsPage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_profile_fields_page

        tpl, perms = _patch_page(_templates())
        with tpl, perms, _patch_resolve(None), pytest.raises(HTTPException) as exc:
            await tenant_profile_fields_page(_request(), "acme", AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_defaults_and_overrides(self):
        from auth.api.routes.admin.tenants_pages import (
            _PROFILE_FIELD_KEYS,
            tenant_profile_fields_page,
        )

        key = _PROFILE_FIELD_KEYS[0]
        templates = _templates()
        tpl, perms = _patch_page(templates)
        with tpl, perms, _patch_resolve(_tenant(settings={"profile_fields": {key: False}})):
            await tenant_profile_fields_page(_request(), "acme", AsyncMock(), _auth())

        fields = templates.TemplateResponse.call_args.kwargs["context"]["fields"]
        assert fields[key] is False
        assert all(v is True for k, v in fields.items() if k != key)


class TestProfileFieldsSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_profile_fields_submit

        with _patch_resolve(None):
            result = await tenant_profile_fields_submit(
                _request(form_data={}), "acme", AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_checked_fields_are_persisted(self):
        from auth.api.routes.admin.tenants_pages import (
            _PROFILE_FIELD_KEYS,
            tenant_profile_fields_submit,
        )

        tenant = _tenant()
        enabled = _PROFILE_FIELD_KEYS[0]

        with _patch_resolve(tenant):
            result = await tenant_profile_fields_submit(
                _request(form_data={enabled: "true"}), "acme", AsyncMock(), _auth()
            )

        assert "success=Profile+fields+updated" in result.headers["location"]
        assert tenant.settings["profile_fields"][enabled] is True

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_profile_fields_submit

        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with _patch_resolve(_tenant()):
            result = await tenant_profile_fields_submit(_request(form_data={}), "acme", db, _auth())

        assert "error=db%20down" in result.headers["location"]


# ---------------------------------------------------------------------------
# Allowed scopes
# ---------------------------------------------------------------------------


def _scope(name="members:read"):
    scope = MagicMock()
    scope.id = uuid.uuid4()
    scope.name = name
    scope.description = "desc"
    scope.resource = name.split(":")[0]
    scope.action = name.split(":")[1]
    scope.category = "org"
    return scope


class TestAllowedScopesPage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_allowed_scopes_page

        tpl, perms = _patch_page(_templates())
        with tpl, perms, _patch_resolve(None), pytest.raises(HTTPException) as exc:
            await tenant_allowed_scopes_page(_request(), "acme", AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_current_selection_is_passed_to_the_template(self):
        from auth.api.routes.admin.tenants_pages import tenant_allowed_scopes_page

        templates = _templates()
        tpl, perms = _patch_page(templates)
        tenant = _tenant(settings={"allowed_scopes": ["members:read"]})

        with (
            tpl,
            perms,
            _patch_resolve(tenant),
            patch(
                f"{TENANTS_PAGES}._scope_service.list_active",
                AsyncMock(return_value=[_scope()]),
            ),
        ):
            await tenant_allowed_scopes_page(_request(), "acme", AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["current_allowed"] == {"members:read"}

    async def test_no_selection_yields_an_empty_set(self):
        from auth.api.routes.admin.tenants_pages import tenant_allowed_scopes_page

        templates = _templates()
        tpl, perms = _patch_page(templates)

        with (
            tpl,
            perms,
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._scope_service.list_active", AsyncMock(return_value=[])),
        ):
            await tenant_allowed_scopes_page(_request(), "acme", AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["current_allowed"] == set()


class TestAllowedScopesSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_allowed_scopes_submit

        with _patch_resolve(None):
            result = await tenant_allowed_scopes_submit(
                _request(form_data={}), "acme", AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_unknown_scopes_are_filtered_out(self):
        from auth.api.routes.admin.tenants_pages import tenant_allowed_scopes_submit

        tenant = _tenant()
        form = {"allowed_scopes": ["members:read", "not:a:scope"]}

        with (
            _patch_resolve(tenant),
            patch(
                f"{TENANTS_PAGES}._scope_service.list_active",
                AsyncMock(return_value=[_scope()]),
            ),
        ):
            result = await tenant_allowed_scopes_submit(
                _request(form_data=form), "acme", AsyncMock(), _auth()
            )

        assert "success=Allowed+scopes+updated" in result.headers["location"]
        assert tenant.settings["allowed_scopes"] == ["members:read"]

    async def test_empty_selection_clears_the_setting(self):
        from auth.api.routes.admin.tenants_pages import tenant_allowed_scopes_submit

        tenant = _tenant()

        with (
            _patch_resolve(tenant),
            patch(f"{TENANTS_PAGES}._scope_service.list_active", AsyncMock(return_value=[])),
        ):
            await tenant_allowed_scopes_submit(_request(form_data={}), "acme", AsyncMock(), _auth())

        assert tenant.settings["allowed_scopes"] is None

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_allowed_scopes_submit

        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._scope_service.list_active", AsyncMock(return_value=[])),
        ):
            result = await tenant_allowed_scopes_submit(_request(form_data={}), "acme", db, _auth())

        assert "error=db%20down" in result.headers["location"]


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------


def _branding():
    branding = MagicMock()
    branding.tenant_id = uuid.uuid4()
    branding.logo_url = None
    branding.logo_dark_url = None
    branding.favicon_url = None
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
    branding.input_background_color = None
    branding.input_focus_background_color = None
    branding.input_border_color = None
    branding.input_focus_border_color = None
    branding.input_text_color = None
    branding.font_family = "sans-serif"
    branding.font_url = None
    branding.custom_css = None
    branding.custom_js = None
    branding.show_powered_by = True
    return branding


class TestBrandingPage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_page

        tpl, perms = _patch_page(_templates())
        with (
            tpl,
            perms,
            _patch_resolve(None, "resolve_with_branding"),
            pytest.raises(HTTPException) as exc,
        ):
            await tenant_branding_page(_request(), "acme", AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_missing_branding_falls_back_to_defaults(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_page
        from auth.services.branding import BrandingConfig

        templates = _templates()
        tpl, perms = _patch_page(templates)

        with tpl, perms, _patch_resolve(_tenant(), "resolve_with_branding"):
            await tenant_branding_page(_request(), "acme", AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["has_branding"] is False
        assert ctx["branding"]["primary_color"] == BrandingConfig().primary_color

    async def test_existing_branding_is_used(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_page

        templates = _templates()
        tpl, perms = _patch_page(templates)
        tenant = _tenant(branding=_branding())

        with tpl, perms, _patch_resolve(tenant, "resolve_with_branding"):
            await tenant_branding_page(_request(), "acme", AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["has_branding"] is True
        assert ctx["branding"]["primary_color"] == "#111111"


class TestBrandingSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_submit

        with _patch_resolve(None, "resolve_with_branding"):
            result = await tenant_branding_submit(
                _request(form_data={}), "acme", AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_missing_branding_row_is_created(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_submit

        tenant = _tenant()

        with (
            _patch_resolve(tenant, "resolve_with_branding"),
            patch(f"{TENANTS_PAGES}._tenant_service.add_branding", AsyncMock()) as add,
        ):
            result = await tenant_branding_submit(
                _request(form_data={"primary_color": "#123456", "show_powered_by": "true"}),
                "acme",
                AsyncMock(),
                _auth(),
            )

        assert "success=Branding+updated" in result.headers["location"]
        add.assert_awaited_once()
        created = add.await_args[0][1]
        assert created.primary_color == "#123456"
        assert created.show_powered_by is True

    async def test_existing_branding_is_updated_with_defaults_for_blanks(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_submit

        branding = _branding()
        tenant = _tenant(branding=branding)

        with _patch_resolve(tenant, "resolve_with_branding"):
            await tenant_branding_submit(
                _request(form_data={"logo_url": "  ", "font_family": "  "}),
                "acme",
                AsyncMock(),
                _auth(),
            )

        assert branding.logo_url is None
        assert branding.primary_color == "#007bff"
        assert branding.font_family.startswith("-apple-system")
        assert branding.show_powered_by is False

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_submit

        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with _patch_resolve(_tenant(branding=_branding()), "resolve_with_branding"):
            result = await tenant_branding_submit(_request(form_data={}), "acme", db, _auth())

        assert "error=db%20down" in result.headers["location"]


class TestBrandingReset:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_reset

        with _patch_resolve(None):
            result = await tenant_branding_reset("acme", AsyncMock(), _auth())

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_existing_branding_is_deleted(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_reset

        branding = _branding()

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_branding",
                AsyncMock(return_value=branding),
            ),
            patch(f"{TENANTS_PAGES}._tenant_service.delete_branding", AsyncMock()) as delete,
        ):
            result = await tenant_branding_reset("acme", AsyncMock(), _auth())

        delete.assert_awaited_once()
        assert "success=Branding+reset" in result.headers["location"]

    async def test_absent_branding_is_a_no_op(self):
        from auth.api.routes.admin.tenants_pages import tenant_branding_reset

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.get_branding", AsyncMock(return_value=None)),
            patch(f"{TENANTS_PAGES}._tenant_service.delete_branding", AsyncMock()) as delete,
        ):
            result = await tenant_branding_reset("acme", AsyncMock(), _auth())

        delete.assert_not_awaited()
        assert result.status_code == 303


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
    """Return a customizable MJML template name, skipping if the build has none."""
    from auth.services.branding import BrandingService

    name = next((t for t in BrandingService.CUSTOMIZABLE_TEMPLATES if t.endswith(".mjml")), None)
    if name is None:
        pytest.skip("no customizable MJML template in this build")
    return name


class TestTemplatesPage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_templates_page

        tpl, perms = _patch_page(_templates())
        with (
            tpl,
            perms,
            _patch_resolve(None, "resolve_with_templates"),
            pytest.raises(HTTPException) as exc,
        ):
            await tenant_templates_page(_request(), "acme", AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_templates_are_sorted_by_name(self):
        from auth.api.routes.admin.tenants_pages import tenant_templates_page

        templates = _templates()
        tpl, perms = _patch_page(templates)
        tenant = _tenant(templates_list=[_template_row("z.html"), _template_row("a.html")])

        with tpl, perms, _patch_resolve(tenant, "resolve_with_templates"):
            await tenant_templates_page(_request(), "acme", AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert [t["template_name"] for t in ctx["tenant_templates"]] == ["a.html", "z.html"]


class TestTemplateEditPage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_page

        tpl, perms = _patch_page(_templates())
        with tpl, perms, _patch_resolve(None), pytest.raises(HTTPException) as exc:
            await tenant_template_edit_page(
                _request(), "acme", _customizable(), AsyncMock(), _auth()
            )

        assert exc.value.status_code == 404

    async def test_non_customizable_template_is_a_400(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_page

        tpl, perms = _patch_page(_templates())
        with tpl, perms, _patch_resolve(_tenant()), pytest.raises(HTTPException) as exc:
            await tenant_template_edit_page(
                _request(), "acme", "secret/internal.html", AsyncMock(), _auth()
            )

        assert exc.value.status_code == 400

    async def test_existing_override_and_default_content_are_rendered(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_page

        templates = _templates()
        tpl, perms = _patch_page(templates)
        name = _customizable()

        with (
            tpl,
            perms,
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_template",
                AsyncMock(return_value=_template_row(name)),
            ),
        ):
            await tenant_template_edit_page(_request(), "acme", name, AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["template"]["template_name"] == name
        assert isinstance(ctx["default_content"], str)

    async def test_missing_override_renders_none(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_page

        templates = _templates()
        tpl, perms = _patch_page(templates)

        with (
            tpl,
            perms,
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.get_template", AsyncMock(return_value=None)),
        ):
            await tenant_template_edit_page(
                _request(), "acme", _customizable(), AsyncMock(), _auth()
            )

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["template"] is None


class TestTemplateEditSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit

        with _patch_resolve(None):
            result = await tenant_template_edit_submit(
                _request(form_data={}), "acme", _customizable(), AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_non_customizable_template_is_rejected(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit

        with _patch_resolve(_tenant()):
            result = await tenant_template_edit_submit(
                _request(form_data={}), "acme", "secret/internal.html", AsyncMock(), _auth()
            )

        assert "error=Template+is+not+customizable" in result.headers["location"]

    async def test_empty_content_is_rejected(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit

        with _patch_resolve(_tenant()):
            result = await tenant_template_edit_submit(
                _request(form_data={"content": "   "}),
                "acme",
                _customizable(),
                AsyncMock(),
                _auth(),
            )

        assert "error=Content+is+required" in result.headers["location"]

    async def test_invalid_jinja_syntax_is_rejected(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit

        name = _customizable()
        with _patch_resolve(_tenant()):
            result = await tenant_template_edit_submit(
                _request(form_data={"content": "{% if %}"}),
                "acme",
                name,
                AsyncMock(),
                _auth(),
            )

        assert "error=Invalid+Jinja2+syntax" in result.headers["location"]

    async def test_valid_html_template_is_saved(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit

        name = _customizable()
        db = AsyncMock()

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.upsert_template", AsyncMock()) as upsert,
        ):
            result = await tenant_template_edit_submit(
                _request(
                    form_data={
                        "content": "<p>{{ name }}</p>",
                        "description": "Login",
                        "is_active": "true",
                    }
                ),
                "acme",
                name,
                db,
                _auth(),
            )

        assert "success=Template+saved" in result.headers["location"]
        assert upsert.await_args.kwargs["is_active"] is True
        db.commit.assert_awaited_once()

    async def test_invalid_mjml_syntax_is_rejected(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit

        name = _customizable_mjml()

        with (
            _patch_resolve(_tenant()),
            patch.dict(
                "sys.modules",
                {"mrml": MagicMock(to_html=MagicMock(side_effect=ValueError("bad mjml")))},
            ),
        ):
            result = await tenant_template_edit_submit(
                _request(form_data={"content": "<mjml>"}),
                "acme",
                name,
                AsyncMock(),
                _auth(),
            )

        assert "error=Invalid+MJML+syntax" in result.headers["location"]

    async def test_mjml_save_invalidates_the_renderer_cache(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit
        from auth.services.branding import BrandingService

        assert BrandingService  # imported for the skip guard below
        name = _customizable_mjml()

        renderer = MagicMock()

        with (
            _patch_resolve(_tenant()),
            patch.dict("sys.modules", {"mrml": MagicMock(to_html=MagicMock())}),
            patch(f"{TENANTS_PAGES}._tenant_service.upsert_template", AsyncMock()),
            patch("auth.services.email_renderer.get_email_renderer", return_value=renderer),
        ):
            result = await tenant_template_edit_submit(
                _request(form_data={"content": "<mjml></mjml>"}),
                "acme",
                name,
                AsyncMock(),
                _auth(),
            )

        assert "success=Template+saved" in result.headers["location"]
        renderer.invalidate_tenant_cache.assert_called_once()

    async def test_save_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_submit

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.upsert_template",
                AsyncMock(side_effect=RuntimeError("db down")),
            ),
        ):
            result = await tenant_template_edit_submit(
                _request(form_data={"content": "<p>ok</p>"}),
                "acme",
                _customizable(),
                AsyncMock(),
                _auth(),
            )

        assert "error=db%20down" in result.headers["location"]


class TestTemplateDelete:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_delete

        with _patch_resolve(None):
            result = await tenant_template_delete("acme", _customizable(), AsyncMock(), _auth())

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_existing_override_is_deleted(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_delete

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_template",
                AsyncMock(return_value=_template_row()),
            ),
            patch(f"{TENANTS_PAGES}._tenant_service.delete_template", AsyncMock()) as delete,
        ):
            result = await tenant_template_delete("acme", _customizable(), AsyncMock(), _auth())

        delete.assert_awaited_once()
        assert "success=Template+deleted" in result.headers["location"]

    async def test_absent_override_is_a_no_op(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_delete

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.get_template", AsyncMock(return_value=None)),
            patch(f"{TENANTS_PAGES}._tenant_service.delete_template", AsyncMock()) as delete,
        ):
            result = await tenant_template_delete("acme", _customizable(), AsyncMock(), _auth())

        delete.assert_not_awaited()
        assert result.status_code == 303


class TestTemplateToggle:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_toggle

        with _patch_resolve(None):
            result = await tenant_template_toggle("acme", _customizable(), AsyncMock(), _auth())

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_missing_override_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_toggle

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.get_template", AsyncMock(return_value=None)),
        ):
            result = await tenant_template_toggle("acme", _customizable(), AsyncMock(), _auth())

        assert "error=Template+not+found" in result.headers["location"]

    @pytest.mark.parametrize(("is_active", "word"), [(True, "enabled"), (False, "disabled")])
    async def test_toggle_reports_the_new_state(self, is_active, word):
        from auth.api.routes.admin.tenants_pages import tenant_template_toggle

        row = _template_row(is_active=is_active)

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.get_template", AsyncMock(return_value=row)),
            patch(f"{TENANTS_PAGES}._tenant_service.toggle_template", AsyncMock()) as toggle,
        ):
            result = await tenant_template_toggle("acme", _customizable(), AsyncMock(), _auth())

        toggle.assert_awaited_once()
        assert f"success=Template+{word}" in result.headers["location"]


# ---------------------------------------------------------------------------
# Trust policy
# ---------------------------------------------------------------------------


class TestTrustModeSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_mode_submit

        with _patch_resolve(None):
            result = await tenant_trust_mode_submit(
                _request(form_data={}), "acme", AsyncMock(), _auth(), AsyncMock()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_unknown_mode_is_rejected(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_mode_submit

        with _patch_resolve(_tenant()):
            result = await tenant_trust_mode_submit(
                _request(form_data={"trust_mode": "wide-open"}),
                "acme",
                AsyncMock(),
                _auth(),
                AsyncMock(),
            )

        assert "error=Invalid+trust+mode" in result.headers["location"]

    async def test_valid_mode_is_applied(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_mode_submit
        from auth.db.models.tenant import TenantTrustMode

        trust_service = AsyncMock()
        db = AsyncMock()

        with _patch_resolve(_tenant()):
            result = await tenant_trust_mode_submit(
                _request(form_data={"trust_mode": TenantTrustMode.ALL.value}),
                "acme",
                db,
                _auth(),
                trust_service,
            )

        trust_service.update_trust_mode.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert "success=Trust+mode+updated" in result.headers["location"]


class TestTrustAddSource:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_add_source

        with _patch_resolve(None):
            result = await tenant_trust_add_source(
                _request(form_data={}), "acme", AsyncMock(), _auth(), AsyncMock()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_missing_selection_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_add_source

        with _patch_resolve(_tenant()):
            result = await tenant_trust_add_source(
                _request(form_data={}), "acme", AsyncMock(), _auth(), AsyncMock()
            )

        assert "error=Please+select+an+organization" in result.headers["location"]

    async def test_unparseable_id_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_add_source

        with _patch_resolve(_tenant()):
            result = await tenant_trust_add_source(
                _request(form_data={"trusted_tenant_id": "not-a-uuid"}),
                "acme",
                AsyncMock(),
                _auth(),
                AsyncMock(),
            )

        assert "error=Invalid+organization+ID" in result.headers["location"]

    async def test_duplicate_source_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_add_source

        trust_service = AsyncMock()
        trust_service.add_trusted_source = AsyncMock(return_value=None)

        with _patch_resolve(_tenant()):
            result = await tenant_trust_add_source(
                _request(form_data={"trusted_tenant_id": str(uuid.uuid4())}),
                "acme",
                AsyncMock(),
                _auth(),
                trust_service,
            )

        assert "error=This+organization+is+already+trusted" in result.headers["location"]

    async def test_new_source_is_added(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_add_source

        trust_service = AsyncMock()
        trust_service.add_trusted_source = AsyncMock(return_value=MagicMock())
        db = AsyncMock()

        with _patch_resolve(_tenant()):
            result = await tenant_trust_add_source(
                _request(
                    form_data={
                        "trusted_tenant_id": str(uuid.uuid4()),
                        "description": " partner ",
                    }
                ),
                "acme",
                db,
                _auth(),
                trust_service,
            )

        assert trust_service.add_trusted_source.await_args[0][3] == "partner"
        db.commit.assert_awaited_once()
        assert "success=Trusted+source+added" in result.headers["location"]


class TestTrustRemoveSource:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_remove_source

        with _patch_resolve(None):
            result = await tenant_trust_remove_source(
                _request(), "acme", str(uuid.uuid4()), AsyncMock(), _auth(), AsyncMock()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_unparseable_id_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_remove_source

        with _patch_resolve(_tenant()):
            result = await tenant_trust_remove_source(
                _request(), "acme", "not-a-uuid", AsyncMock(), _auth(), AsyncMock()
            )

        assert "error=Invalid+source+ID" in result.headers["location"]

    async def test_missing_source_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_remove_source

        trust_service = AsyncMock()
        trust_service.remove_trusted_source = AsyncMock(return_value=False)

        with _patch_resolve(_tenant()):
            result = await tenant_trust_remove_source(
                _request(), "acme", str(uuid.uuid4()), AsyncMock(), _auth(), trust_service
            )

        assert "error=Trusted+source+not+found" in result.headers["location"]

    async def test_source_is_removed(self):
        from auth.api.routes.admin.tenants_pages import tenant_trust_remove_source

        trust_service = AsyncMock()
        trust_service.remove_trusted_source = AsyncMock(return_value=True)
        db = AsyncMock()

        with _patch_resolve(_tenant()):
            result = await tenant_trust_remove_source(
                _request(), "acme", str(uuid.uuid4()), db, _auth(), trust_service
            )

        db.commit.assert_awaited_once()
        assert "success=Trusted+source+removed" in result.headers["location"]


# ---------------------------------------------------------------------------
# Custom roles
# ---------------------------------------------------------------------------


def _custom_role(is_system=False):
    role = MagicMock()
    role.id = uuid.uuid4()
    role.name = "editor"
    role.display_name = "Editor"
    role.description = None
    role.scopes = ["members:read"]
    role.is_system = is_system
    return role


class TestRoleCreatePage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_create_page

        tpl, _perms = _patch_page(_templates())
        with tpl, _patch_resolve(None), pytest.raises(HTTPException) as exc:
            await tenant_role_create_page(_request(), "acme", AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_renders_the_blank_form(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_create_page

        templates = _templates()
        tpl, _perms = _patch_page(templates)

        with tpl, _patch_resolve(_tenant()):
            await tenant_role_create_page(_request(), "acme", AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["role"] is None
        assert ctx["form_title"] == "Create Role"


class TestRoleCreateSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_create_submit

        with _patch_resolve(None):
            result = await tenant_role_create_submit(
                _request(form_data={}), "acme", AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_name_is_required(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_create_submit

        with _patch_resolve(_tenant()):
            result = await tenant_role_create_submit(
                _request(form_data={"display_name": "Editor"}), "acme", AsyncMock(), _auth()
            )

        assert "error=Name+is+required" in result.headers["location"]

    async def test_display_name_is_required(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_create_submit

        with _patch_resolve(_tenant()):
            result = await tenant_role_create_submit(
                _request(form_data={"name": "editor"}), "acme", AsyncMock(), _auth()
            )

        assert "error=Display+name+is+required" in result.headers["location"]

    async def test_role_is_created(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_create_submit

        db = AsyncMock()
        form = {
            "name": " EDITOR ",
            "display_name": "Editor",
            "description": " Edits things ",
            "scopes": ["members:read"],
        }

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}.tenant_role_service.create_role", AsyncMock()) as create,
        ):
            result = await tenant_role_create_submit(_request(form_data=form), "acme", db, _auth())

        assert create.await_args[0][2] == "editor"
        assert create.await_args[0][5] == "Edits things"
        db.commit.assert_awaited_once()
        assert "success=Role+created+successfully" in result.headers["location"]

    async def test_validation_error_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_create_submit

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}.tenant_role_service.create_role",
                AsyncMock(side_effect=ValueError("Role already exists")),
            ),
        ):
            result = await tenant_role_create_submit(
                _request(form_data={"name": "editor", "display_name": "Editor"}),
                "acme",
                AsyncMock(),
                _auth(),
            )

        assert "error=Role%20already%20exists" in result.headers["location"]


class TestRoleEditPage:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_page

        tpl, _perms = _patch_page(_templates())
        with tpl, _patch_resolve(None), pytest.raises(HTTPException) as exc:
            await tenant_role_edit_page(_request(), "acme", str(uuid.uuid4()), AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_unparseable_role_id_is_a_400(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_page

        tpl, _perms = _patch_page(_templates())
        with tpl, _patch_resolve(_tenant()), pytest.raises(HTTPException) as exc:
            await tenant_role_edit_page(_request(), "acme", "not-a-uuid", AsyncMock(), _auth())

        assert exc.value.status_code == 400

    async def test_missing_role_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_page

        tpl, _perms = _patch_page(_templates())
        with (
            tpl,
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=None),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await tenant_role_edit_page(_request(), "acme", str(uuid.uuid4()), AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_renders_the_populated_form(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_page

        templates = _templates()
        tpl, _perms = _patch_page(templates)
        role = _custom_role()

        with (
            tpl,
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
        ):
            await tenant_role_edit_page(_request(), "acme", str(role.id), AsyncMock(), _auth())

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["role"] is role
        assert ctx["form_title"] == "Edit Role: Editor"


class TestRoleEditSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_submit

        with _patch_resolve(None):
            result = await tenant_role_edit_submit(
                _request(form_data={}), "acme", str(uuid.uuid4()), AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_unparseable_role_id_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_submit

        with _patch_resolve(_tenant()):
            result = await tenant_role_edit_submit(
                _request(form_data={}), "acme", "not-a-uuid", AsyncMock(), _auth()
            )

        assert "error=Invalid+role+ID" in result.headers["location"]

    async def test_missing_role_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_submit

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=None),
            ),
        ):
            result = await tenant_role_edit_submit(
                _request(form_data={}), "acme", str(uuid.uuid4()), AsyncMock(), _auth()
            )

        assert "error=Role+not+found" in result.headers["location"]

    async def test_display_name_is_required(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_submit

        role = _custom_role()

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
        ):
            result = await tenant_role_edit_submit(
                _request(form_data={}), "acme", str(role.id), AsyncMock(), _auth()
            )

        assert "error=Display+name+is+required" in result.headers["location"]

    async def test_custom_role_scopes_are_updated(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_submit

        role = _custom_role()
        form = {"display_name": "Editor", "scopes": ["members:write"]}

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
            patch(f"{TENANTS_PAGES}.tenant_role_service.update_role", AsyncMock()) as update,
        ):
            result = await tenant_role_edit_submit(
                _request(form_data=form), "acme", str(role.id), AsyncMock(), _auth()
            )

        assert update.await_args[0][3] == ["members:write"]
        assert "success=Role+updated+successfully" in result.headers["location"]

    async def test_system_role_scopes_are_left_alone(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_submit

        role = _custom_role(is_system=True)
        form = {"display_name": "Editor", "scopes": ["members:write"]}

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
            patch(f"{TENANTS_PAGES}.tenant_role_service.update_role", AsyncMock()) as update,
        ):
            await tenant_role_edit_submit(
                _request(form_data=form), "acme", str(role.id), AsyncMock(), _auth()
            )

        assert update.await_args[0][3] is None

    async def test_validation_error_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_edit_submit

        role = _custom_role()

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
            patch(
                f"{TENANTS_PAGES}.tenant_role_service.update_role",
                AsyncMock(side_effect=ValueError("Invalid scopes")),
            ),
        ):
            result = await tenant_role_edit_submit(
                _request(form_data={"display_name": "Editor"}),
                "acme",
                str(role.id),
                AsyncMock(),
                _auth(),
            )

        assert "error=Invalid%20scopes" in result.headers["location"]


class TestRoleDeleteSubmit:
    async def test_unknown_tenant_redirects_to_the_list(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_delete_submit

        with _patch_resolve(None):
            result = await tenant_role_delete_submit(
                "acme", str(uuid.uuid4()), AsyncMock(), _auth()
            )

        assert "error=Tenant+not+found" in result.headers["location"]

    async def test_unparseable_role_id_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_delete_submit

        with _patch_resolve(_tenant()):
            result = await tenant_role_delete_submit("acme", "not-a-uuid", AsyncMock(), _auth())

        assert "error=Invalid+role+ID" in result.headers["location"]

    async def test_missing_role_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_delete_submit

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=None),
            ),
        ):
            result = await tenant_role_delete_submit(
                "acme", str(uuid.uuid4()), AsyncMock(), _auth()
            )

        assert "error=Role+not+found" in result.headers["location"]

    async def test_system_roles_cannot_be_deleted(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_delete_submit

        role = _custom_role(is_system=True)

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
        ):
            result = await tenant_role_delete_submit("acme", str(role.id), AsyncMock(), _auth())

        assert "error=Cannot+delete+system+roles" in result.headers["location"]

    async def test_role_with_members_cannot_be_deleted(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_delete_submit

        role = _custom_role()

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
            patch(
                f"{TENANTS_PAGES}._tenant_service.count_members_for_role",
                AsyncMock(return_value=3),
            ),
        ):
            result = await tenant_role_delete_submit("acme", str(role.id), AsyncMock(), _auth())

        assert "error=Cannot+delete+role+with+3+assigned+members" in result.headers["location"]

    async def test_unused_role_is_deleted(self):
        from auth.api.routes.admin.tenants_pages import tenant_role_delete_submit

        role = _custom_role()
        db = AsyncMock()

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_custom_role_scoped",
                AsyncMock(return_value=role),
            ),
            patch(
                f"{TENANTS_PAGES}._tenant_service.count_members_for_role",
                AsyncMock(return_value=0),
            ),
            patch(f"{TENANTS_PAGES}._tenant_service.delete_custom_role", AsyncMock()) as delete,
        ):
            result = await tenant_role_delete_submit("acme", str(role.id), db, _auth())

        delete.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert "success=Role+deleted+successfully" in result.headers["location"]


# ---------------------------------------------------------------------------
# Remaining branches in the tenant detail / IdP handlers
# ---------------------------------------------------------------------------


def _member(user_id=None, role_name="member"):
    member = MagicMock()
    member.id = uuid.uuid4()
    member.user_id = user_id or uuid.uuid4()
    member.tenant_id = uuid.uuid4()
    member.role_name = role_name
    member.role_display_name = role_name.capitalize()
    member.role_id = uuid.uuid4()
    member.joined_at = _now()
    member.invited_at = _now()
    member.created_at = _now()
    member.user = MagicMock()
    member.user.profile = MagicMock()
    member.user.profile.name = "Test User"
    member.custom_role = MagicMock()
    member.custom_role.name = role_name
    member.custom_role.display_name = role_name.capitalize()
    return member


def _idp(tenant_id=None):
    from auth.db.models.tenant import IdentityProviderType

    idp = MagicMock()
    idp.id = uuid.uuid4()
    idp.tenant_id = tenant_id or uuid.uuid4()
    idp.name = "Google SSO"
    idp.provider_type = IdentityProviderType.OIDC
    idp.client_id = "cid"
    idp.client_secret_encrypted = b"enc"
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


class TestTenantDetailPageMemberEmails:
    async def test_member_emails_are_resolved(self):
        from auth.api.routes.admin.tenants_pages import tenant_detail_page

        templates = _templates()
        tpl, perms = _patch_page(templates)
        tenant = _tenant()
        tenant.members = [_member(role_name="owner")]

        with (
            tpl,
            perms,
            _patch_resolve(tenant, "resolve_with_detail"),
            patch(
                f"{TENANTS_PAGES}._tenant_service.get_member_primary_email",
                AsyncMock(return_value="member@example.com"),
            ) as get_email,
            patch(
                f"{TENANTS_PAGES}._tenant_service.list_active_dropdown",
                AsyncMock(return_value=[]),
            ),
        ):
            trust_service = AsyncMock()
            trust_service.get_tenant_trust_config = AsyncMock(
                return_value={"trust_mode": "none", "trusted_sources": []}
            )
            await tenant_detail_page(_request(), "acme", AsyncMock(), _auth(), trust_service)

        get_email.assert_awaited_once()
        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["members"][0]["user_email"] == "member@example.com"


class TestTenantIdpCreateSubmitBranches:
    async def test_unknown_provider_type_falls_back_to_oidc(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_submit
        from auth.db.models.tenant import IdentityProviderType

        tenant = _tenant()
        staged = {}

        async def _add(_db, idp):
            staged["idp"] = idp
            idp.id = uuid.uuid4()

        with (
            _patch_resolve(tenant),
            patch(f"{TENANTS_PAGES}._tenant_service.add_idp", AsyncMock(side_effect=_add)),
        ):
            result = await tenant_idp_create_submit(
                _request(
                    form_data={
                        "name": "IdP",
                        "client_id": "cid",
                        "provider_type": "carrier-pigeon",
                    }
                ),
                "acme",
                AsyncMock(),
                _auth(),
            )

        assert "success=Identity+provider+created" in result.headers["location"]
        assert staged["idp"].provider_type is IdentityProviderType.OIDC
        assert staged["idp"].client_secret_encrypted is None

    async def test_client_secret_is_encrypted(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_submit

        staged = {}

        async def _add(_db, idp):
            staged["idp"] = idp
            idp.id = uuid.uuid4()

        encryption = MagicMock()
        encryption.encrypt.return_value = b"cipher"

        with (
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.add_idp", AsyncMock(side_effect=_add)),
            patch(f"{TENANTS_PAGES}.get_encryption", return_value=encryption),
        ):
            await tenant_idp_create_submit(
                _request(form_data={"name": "IdP", "client_id": "cid", "client_secret": "s3cr3t"}),
                "acme",
                AsyncMock(),
                _auth(),
            )

        encryption.encrypt.assert_called_once_with(b"s3cr3t")
        assert staged["idp"].client_secret_encrypted == b"cipher"

    async def test_persistence_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_submit

        with (
            _patch_resolve(_tenant()),
            patch(
                f"{TENANTS_PAGES}._tenant_service.add_idp",
                AsyncMock(side_effect=RuntimeError("db down")),
            ),
        ):
            result = await tenant_idp_create_submit(
                _request(form_data={"name": "IdP", "client_id": "cid"}),
                "acme",
                AsyncMock(),
                _auth(),
            )

        assert "error=db%20down" in result.headers["location"]


class TestTenantIdpEditPageErrors:
    async def test_unknown_tenant_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_page

        tpl, perms = _patch_page(_templates())
        with tpl, perms, _patch_resolve(None), pytest.raises(HTTPException) as exc:
            await tenant_idp_edit_page(_request(), "acme", str(uuid.uuid4()), AsyncMock(), _auth())

        assert exc.value.status_code == 404

    async def test_missing_idp_is_a_404(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_page

        tpl, perms = _patch_page(_templates())
        with (
            tpl,
            perms,
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.get_idp_scoped", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await tenant_idp_edit_page(_request(), "acme", str(uuid.uuid4()), AsyncMock(), _auth())

        assert exc.value.status_code == 404


class TestTenantIdpEditSubmitBranches:
    async def test_unparseable_idp_id_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_submit

        with _patch_resolve(_tenant()):
            result = await tenant_idp_edit_submit(
                _request(form_data={}), "acme", "not-a-uuid", AsyncMock(), _auth()
            )

        assert "error=Invalid+IdP+ID" in result.headers["location"]

    async def test_new_secret_is_encrypted(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_submit

        tenant = _tenant()
        idp = _idp(tenant.id)
        encryption = MagicMock()
        encryption.encrypt.return_value = b"cipher"

        with (
            _patch_resolve(tenant),
            patch(f"{TENANTS_PAGES}._tenant_service.get_idp_scoped", AsyncMock(return_value=idp)),
            patch(f"{TENANTS_PAGES}.get_encryption", return_value=encryption),
        ):
            result = await tenant_idp_edit_submit(
                _request(form_data={"name": "IdP", "client_id": "cid", "client_secret": "rotated"}),
                "acme",
                str(idp.id),
                AsyncMock(),
                _auth(),
            )

        encryption.encrypt.assert_called_once_with(b"rotated")
        assert idp.client_secret_encrypted == b"cipher"
        assert "success=Identity+provider+updated" in result.headers["location"]

    async def test_commit_failure_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_submit

        tenant = _tenant()
        idp = _idp(tenant.id)
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            _patch_resolve(tenant),
            patch(f"{TENANTS_PAGES}._tenant_service.get_idp_scoped", AsyncMock(return_value=idp)),
        ):
            result = await tenant_idp_edit_submit(
                _request(form_data={"name": "IdP", "client_id": "cid"}),
                "acme",
                str(idp.id),
                db,
                _auth(),
            )

        assert "error=db%20down" in result.headers["location"]


class TestTenantIdpToggleInvalidId:
    async def test_unparseable_idp_id_is_reported(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_toggle_submit

        with _patch_resolve(_tenant()):
            result = await tenant_idp_toggle_submit("acme", "not-a-uuid", AsyncMock(), _auth())

        assert "error=Invalid+IdP+ID" in result.headers["location"]


class TestTemplateEditPageMissingDefaultFile:
    async def test_absent_default_file_yields_empty_content(self):
        from auth.api.routes.admin.tenants_pages import tenant_template_edit_page

        templates = _templates()
        tpl, perms = _patch_page(templates)

        missing = MagicMock()
        missing.exists.return_value = False
        templates_dir = MagicMock()
        templates_dir.__truediv__ = MagicMock(return_value=missing)
        path_cls = MagicMock()
        path_cls.return_value.parent.parent.parent.parent.__truediv__ = MagicMock(
            return_value=templates_dir
        )

        with (
            tpl,
            perms,
            _patch_resolve(_tenant()),
            patch(f"{TENANTS_PAGES}._tenant_service.get_template", AsyncMock(return_value=None)),
            patch("pathlib.Path", path_cls),
        ):
            await tenant_template_edit_page(
                _request(), "acme", _customizable(), AsyncMock(), _auth()
            )

        ctx = templates.TemplateResponse.call_args.kwargs["context"]
        assert ctx["default_content"] == ""
