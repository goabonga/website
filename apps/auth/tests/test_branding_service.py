# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.branding — BrandingService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.branding import (
    BrandingConfig,
    BrandingService,
    TenantTemplateLoader,
)
from jinja2 import TemplateNotFound

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


# ── BrandingConfig ──────────────────────────────────────────────────────────


class TestBrandingConfig:
    def test_defaults(self):
        bc = BrandingConfig()
        assert bc.primary_color == "#e94560"
        assert bc.display_name == ""
        assert bc.show_powered_by is True
        assert bc.logo_url is None

    def test_from_tenant_none(self):
        bc = BrandingConfig.from_tenant(None)
        assert bc.display_name == ""

    def test_from_tenant_no_branding(self):
        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        tenant.slug = "test"
        tenant.display_name = "Test"
        tenant.branding = None
        bc = BrandingConfig.from_tenant(tenant)
        assert bc.tenant_slug == "test"
        assert bc.display_name == "Test"
        assert bc.primary_color == "#e94560"  # default

    def test_from_tenant_with_branding(self):
        branding = MagicMock()
        branding.logo_url = "https://example.com/logo.png"
        branding.logo_dark_url = None
        branding.favicon_url = None
        branding.primary_color = "#ff0000"
        branding.secondary_color = "#00ff00"
        branding.accent_color = "#0000ff"
        branding.background_color = "#111"
        branding.surface_color = "#222"
        branding.text_color = "#fff"
        branding.text_muted_color = "#aaa"
        branding.error_color = "#f00"
        branding.success_color = "#0f0"
        branding.border_color = "#333"
        branding.warning_color = "#ff0"
        branding.info_color = "#00f"
        branding.font_family = "Arial"
        branding.font_url = "https://fonts.example.com/arial.css"
        branding.custom_css = "body{color:red}"
        branding.custom_js = "console.log('hi')"
        branding.show_powered_by = False

        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        tenant.slug = "test"
        tenant.display_name = "Test"
        tenant.branding = branding

        bc = BrandingConfig.from_tenant(tenant)
        assert bc.logo_url == "https://example.com/logo.png"
        assert bc.primary_color == "#ff0000"
        assert bc.font_family == "Arial"
        assert bc.custom_css == "body{color:red}"
        assert bc.show_powered_by is False

    def test_from_tenant_branding_none_custom_fields(self):
        branding = MagicMock()
        branding.logo_url = None
        branding.logo_dark_url = None
        branding.favicon_url = None
        branding.primary_color = "#e94560"
        branding.secondary_color = "#0f3460"
        branding.accent_color = "#e94560"
        branding.background_color = "#1a1a2e"
        branding.surface_color = "#16213e"
        branding.text_color = "#e0e0e0"
        branding.text_muted_color = "#a0a0a0"
        branding.error_color = "#ff6b6b"
        branding.success_color = "#00b894"
        branding.border_color = "#0f3460"
        branding.warning_color = "#fdcb6e"
        branding.info_color = "#74b9ff"
        branding.font_family = "sans-serif"
        branding.font_url = None
        branding.custom_css = None
        branding.custom_js = None
        branding.show_powered_by = True

        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        tenant.slug = "t"
        tenant.display_name = "T"
        tenant.branding = branding

        bc = BrandingConfig.from_tenant(tenant)
        assert bc.custom_css == ""
        assert bc.custom_js == ""

    def test_to_css_variables(self):
        bc = BrandingConfig()
        css = bc.to_css_variables()
        assert "--primary-color:" in css
        assert "--font-family:" in css

    def test_get_font_import_with_url(self):
        bc = BrandingConfig(font_url="https://fonts.example.com/font.css")
        assert "@import url" in bc.get_font_import()

    def test_get_font_import_without_url(self):
        bc = BrandingConfig()
        assert bc.get_font_import() == ""


# ── TenantTemplateLoader ───────────────────────────────────────────────────


class TestTenantTemplateLoader:
    def test_get_source_filesystem(self, tmp_path):
        template_file = tmp_path / "test.html"
        template_file.write_text("<h1>Hello</h1>")
        loader = TenantTemplateLoader(tmp_path, None)
        source, filename, uptodate_fn = loader.get_source(None, "test.html")
        assert "<h1>Hello</h1>" in source
        assert uptodate_fn()

    def test_get_source_not_found(self, tmp_path):
        loader = TenantTemplateLoader(tmp_path, None)
        with pytest.raises(TemplateNotFound):
            loader.get_source(None, "missing.html")

    @pytest.mark.asyncio
    async def test_get_source_async_db_template(self, db, tmp_path):
        loader = TenantTemplateLoader(tmp_path, None)
        tid = uuid.uuid4()
        db_template = MagicMock()
        db_template.content = "<h1>DB Template</h1>"
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=db_template))

        source, filename, is_from_db = await loader.get_source_async(
            db, "auth/login.html", tenant_id=tid
        )
        assert source == "<h1>DB Template</h1>"
        assert is_from_db is True

    @pytest.mark.asyncio
    async def test_get_source_async_filesystem_fallback(self, db, tmp_path):
        loader = TenantTemplateLoader(tmp_path, None)
        tid = uuid.uuid4()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        template_file = tmp_path / "auth"
        template_file.mkdir()
        (template_file / "login.html").write_text("<h1>FS</h1>")

        source, filename, is_from_db = await loader.get_source_async(
            db, "auth/login.html", tenant_id=tid
        )
        assert "<h1>FS</h1>" in source
        assert is_from_db is False

    @pytest.mark.asyncio
    async def test_get_source_async_no_tenant(self, db, tmp_path):
        loader = TenantTemplateLoader(tmp_path, None)
        template_file = tmp_path / "test.html"
        template_file.write_text("<h1>No Tenant</h1>")

        source, filename, is_from_db = await loader.get_source_async(
            db, "test.html", tenant_id=None
        )
        assert "<h1>No Tenant</h1>" in source
        assert is_from_db is False

    @pytest.mark.asyncio
    async def test_get_source_async_not_found(self, db, tmp_path):
        loader = TenantTemplateLoader(tmp_path, None)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        with pytest.raises(TemplateNotFound):
            await loader.get_source_async(db, "missing.html", tenant_id=uuid.uuid4())


# ── BrandingService ────────────────────────────────────────────────────────


class TestBrandingService:
    @pytest.fixture
    def svc(self, tmp_path):
        return BrandingService(tmp_path, None)

    @pytest.mark.asyncio
    async def test_get_branding_no_tenant(self, db, svc):
        result = await svc.get_branding(db, tenant_id=None)
        assert isinstance(result, BrandingConfig)
        assert result.display_name == ""

    @pytest.mark.asyncio
    async def test_get_branding_with_tenant(self, db, svc):
        tenant = MagicMock()
        tenant.branding = None
        tenant.id = uuid.uuid4()
        tenant.slug = "test"
        tenant.display_name = "Test"
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        result = await svc.get_branding(db, tenant.id)
        assert result.display_name == "Test"

    @pytest.mark.asyncio
    async def test_get_branding_tenant_not_found(self, db, svc):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await svc.get_branding(db, uuid.uuid4())
        assert result.display_name == ""

    @pytest.mark.asyncio
    async def test_get_branding_for_current_tenant(self, db, svc):
        ctx = MagicMock()
        ctx.tenant_id = uuid.uuid4()
        svc.get_branding = AsyncMock(return_value=BrandingConfig(display_name="Ctx"))
        with patch("auth.services.branding.get_tenant_context", return_value=ctx):
            result = await svc.get_branding_for_current_tenant(db)
        assert result.display_name == "Ctx"

    @pytest.mark.asyncio
    async def test_get_branding_for_current_tenant_no_context(self, db, svc):
        svc.get_branding = AsyncMock(return_value=BrandingConfig())
        with patch("auth.services.branding.get_tenant_context", return_value=None):
            result = await svc.get_branding_for_current_tenant(db)
        assert isinstance(result, BrandingConfig)

    @pytest.mark.asyncio
    async def test_render_template(self, db, tmp_path):
        (tmp_path / "test.html").write_text("Hello {{ name }}")
        svc = BrandingService(tmp_path, None)
        svc.get_branding = AsyncMock(return_value=BrandingConfig())

        result = await svc.render_template(db, "test.html", {"name": "World"})
        assert "Hello World" in result

    @pytest.mark.asyncio
    async def test_render_template_with_existing_branding(self, db, tmp_path):
        (tmp_path / "test.html").write_text("{{ branding.display_name }}")
        svc = BrandingService(tmp_path, None)
        branding = BrandingConfig(display_name="Custom")
        result = await svc.render_template(db, "test.html", {"branding": branding})
        assert "Custom" in result

    @pytest.mark.asyncio
    async def test_get_tenant_templates(self, db, svc):
        t1 = MagicMock()
        t2 = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[t1, t2]))
        result = await svc.get_tenant_templates(db, uuid.uuid4())
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_template_found(self, db, svc):
        tmpl = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tmpl))
        result = await svc.get_template(db, uuid.uuid4(), "auth/login.html")
        assert result is tmpl

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, db, svc):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await svc.get_template(db, uuid.uuid4(), "missing.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_template_new(self, db, svc):
        svc.get_template = AsyncMock(return_value=None)
        await svc.save_template(db, uuid.uuid4(), "auth/login.html", "<h1>New</h1>")
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_template_update(self, db, svc):
        existing = MagicMock()
        svc.get_template = AsyncMock(return_value=existing)
        await svc.save_template(db, uuid.uuid4(), "auth/login.html", "<h1>Updated</h1>", "desc")
        assert existing.content == "<h1>Updated</h1>"
        assert existing.description == "desc"

    @pytest.mark.asyncio
    async def test_delete_template_found(self, db, svc):
        tmpl = MagicMock()
        svc.get_template = AsyncMock(return_value=tmpl)
        result = await svc.delete_template(db, uuid.uuid4(), "auth/login.html")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_template_not_found(self, db, svc):
        svc.get_template = AsyncMock(return_value=None)
        result = await svc.delete_template(db, uuid.uuid4(), "missing.html")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_default_template_content(self, tmp_path):
        (tmp_path / "test.html").write_text("<h1>Default</h1>")
        svc = BrandingService(tmp_path, None)
        result = await svc.get_default_template_content("test.html")
        assert result == "<h1>Default</h1>"

    @pytest.mark.asyncio
    async def test_get_default_template_content_not_found(self, tmp_path):
        svc = BrandingService(tmp_path, None)
        result = await svc.get_default_template_content("missing.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_branding_new(self, db, svc):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        await svc.save_branding(db, uuid.uuid4(), primary_color="#ff0000")
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_branding_update(self, db, svc):
        existing = MagicMock()
        existing.primary_color = "#old"
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=existing))
        await svc.save_branding(db, uuid.uuid4(), primary_color="#new")
        assert existing.primary_color == "#new"

    @pytest.mark.asyncio
    async def test_delete_branding_found(self, db, svc):
        branding = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=branding))
        result = await svc.delete_branding(db, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_branding_not_found(self, db, svc):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await svc.delete_branding(db, uuid.uuid4())
        assert result is False

    def test_customizable_templates(self, svc):
        assert len(svc.CUSTOMIZABLE_TEMPLATES) > 0
        assert "auth/login.html" in svc.CUSTOMIZABLE_TEMPLATES


# ── get_branding_record ─────────────────────────────────────────────────────


class TestGetBrandingRecord:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db):
        service = _branding_service()
        record = MagicMock()
        service._repo.find_branding = AsyncMock(return_value=record)
        tenant_id = uuid.uuid4()

        assert await service.get_branding_record(db, tenant_id) is record
        service._repo.find_branding.assert_awaited_once_with(db, tenant_id)


# ── get_branding_for_current_tenant ─────────────────────────────────────────


class TestGetBrandingForCurrentTenant:
    def _ctx(self, tenant_id):
        ctx = MagicMock()
        ctx.tenant_id = tenant_id
        return ctx

    @pytest.mark.asyncio
    async def test_no_context_uses_defaults(self, db):
        service = _branding_service()
        service.get_branding = AsyncMock(return_value="cfg")

        with patch("auth.services.branding.get_tenant_context", return_value=None):
            assert await service.get_branding_for_current_tenant(db) == "cfg"

        service.get_branding.assert_awaited_once_with(db, None)

    @pytest.mark.asyncio
    async def test_uuid_context_is_used_directly(self, db):
        service = _branding_service()
        service.get_branding = AsyncMock(return_value="cfg")
        tenant_id = uuid.uuid4()

        with patch("auth.services.branding.get_tenant_context", return_value=self._ctx(tenant_id)):
            await service.get_branding_for_current_tenant(db)

        service.get_branding.assert_awaited_once_with(db, tenant_id)

    @pytest.mark.asyncio
    async def test_string_context_is_parsed(self, db):
        service = _branding_service()
        service.get_branding = AsyncMock(return_value="cfg")
        tenant_id = uuid.uuid4()

        with patch(
            "auth.services.branding.get_tenant_context", return_value=self._ctx(str(tenant_id))
        ):
            await service.get_branding_for_current_tenant(db)

        service.get_branding.assert_awaited_once_with(db, tenant_id)

    @pytest.mark.asyncio
    async def test_unparseable_string_falls_back_to_defaults(self, db):
        service = _branding_service()
        service.get_branding = AsyncMock(return_value="cfg")

        with patch(
            "auth.services.branding.get_tenant_context", return_value=self._ctx("not-a-uuid")
        ):
            await service.get_branding_for_current_tenant(db)

        service.get_branding.assert_awaited_once_with(db, None)


# ── save_branding ───────────────────────────────────────────────────────────


class TestSaveBrandingIgnoresUnknownFields:
    @pytest.mark.asyncio
    async def test_unknown_kwarg_is_skipped(self, db):
        service = _branding_service()
        existing = MagicMock(spec=["primary_color"])
        existing.primary_color = "#000"
        service._repo.find_branding = AsyncMock(return_value=existing)
        service._repo.flush = AsyncMock()

        result = await service.save_branding(
            db, uuid.uuid4(), primary_color="#fff", not_a_column="ignored"
        )

        assert result is existing
        assert existing.primary_color == "#fff"
        assert not hasattr(existing, "not_a_column")
        service._repo.flush.assert_awaited_once_with(db)


def _branding_service():
    """Build a BrandingService with stub template path / session factory."""
    from pathlib import Path

    from auth.services.branding import BrandingService

    return BrandingService(Path("/nonexistent/templates"), MagicMock())
