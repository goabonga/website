# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.email_renderer — EmailRenderer."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.branding import BrandingConfig
from auth.services.email_renderer import (
    BRANDING_FIELDS,
    EmailRenderer,
    get_email_renderer,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    import auth.services.email_renderer as mod

    mod._renderer = None
    yield
    mod._renderer = None


@pytest.fixture
def renderer():
    return EmailRenderer()


@pytest.fixture
def db():
    session = AsyncMock()
    return session


# ── constants ───────────────────────────────────────────────────────────────


class TestConstants:
    def test_branding_fields(self):
        assert "primary_color" in BRANDING_FIELDS
        assert "display_name" in BRANDING_FIELDS
        assert "logo_url" in BRANDING_FIELDS


# ── EmailRenderer init ──────────────────────────────────────────────────────


class TestInit:
    def test_default_state(self, renderer):
        assert renderer._compiled_cache == {}
        assert renderer._tenant_cache == {}


# ── _load_mjml ──────────────────────────────────────────────────────────────


class TestLoadMjml:
    def test_found(self, renderer, tmp_path):
        with patch("auth.services.email_renderer.MJML_DIR", tmp_path):
            (tmp_path / "test.mjml").write_text("<mjml>Hello</mjml>")
            result = renderer._load_mjml("test")
        assert result == "<mjml>Hello</mjml>"

    def test_not_found(self, renderer, tmp_path):
        with patch("auth.services.email_renderer.MJML_DIR", tmp_path):
            result = renderer._load_mjml("missing")
        assert result is None


# ── _load_txt ───────────────────────────────────────────────────────────────


class TestLoadTxt:
    def test_found(self, renderer, tmp_path):
        with patch("auth.services.email_renderer.TXT_DIR", tmp_path):
            (tmp_path / "test.txt").write_text("Hello text")
            result = renderer._load_txt("test")
        assert result == "Hello text"

    def test_not_found(self, renderer, tmp_path):
        with patch("auth.services.email_renderer.TXT_DIR", tmp_path):
            result = renderer._load_txt("missing")
        assert result is None


# ── _compile_mjml ───────────────────────────────────────────────────────────


class TestCompileMjml:
    def test_converts_percent_vars(self, renderer):
        mock_result = MagicMock()
        mock_result.content = "<p>%name%</p>"
        with patch("mrml.to_html", return_value=mock_result):
            result = renderer._compile_mjml("<mjml>%name%</mjml>")
        assert "{{name}}" in result

    def test_normalizes_newlines(self, renderer):
        mock_result = MagicMock()
        mock_result.content = "<p>ok</p>"
        with patch("mrml.to_html", return_value=mock_result) as mock_fn:
            renderer._compile_mjml("line1\r\nline2\rline3")
            called_source = mock_fn.call_args[0][0]
            assert "\r" not in called_source


# ── _get_compiled_html ──────────────────────────────────────────────────────


class TestGetCompiledHtml:
    def test_cached(self, renderer):
        renderer._compiled_cache["test"] = "<p>cached</p>"
        assert renderer._get_compiled_html("test") == "<p>cached</p>"

    def test_compile_and_cache(self, renderer):
        renderer._load_mjml = MagicMock(return_value="<mjml></mjml>")
        renderer._compile_mjml = MagicMock(return_value="<p>compiled</p>")
        result = renderer._get_compiled_html("test")
        assert result == "<p>compiled</p>"
        assert "test" in renderer._compiled_cache

    def test_no_mjml_source(self, renderer):
        renderer._load_mjml = MagicMock(return_value=None)
        result = renderer._get_compiled_html("missing")
        assert result is None

    def test_compilation_error(self, renderer):
        renderer._load_mjml = MagicMock(return_value="<mjml></mjml>")
        renderer._compile_mjml = MagicMock(side_effect=Exception("compile fail"))
        result = renderer._get_compiled_html("bad")
        assert result is None


# ── _render_jinja ───────────────────────────────────────────────────────────


class TestRenderJinja:
    def test_basic(self, renderer):
        result = renderer._render_jinja("Hello {{ name }}", {"name": "World"})
        assert result == "Hello World"


# ── _html_to_plain_text ────────────────────────────────────────────────────


class TestHtmlToPlainText:
    def test_basic(self, renderer):
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        result = renderer._html_to_plain_text(html)
        assert "Hello" in result
        assert "World" in result
        assert "alert" not in result

    def test_error_returns_empty(self, renderer):
        with patch("bs4.BeautifulSoup", side_effect=Exception("fail")):
            result = renderer._html_to_plain_text("<p>test</p>")
        assert result == ""


# ── render_email ────────────────────────────────────────────────────────────


class TestRenderEmail:
    def test_success_with_txt(self, renderer):
        renderer._get_compiled_html = MagicMock(return_value="<p>Hello {{ name }}</p>")
        renderer._load_txt = MagicMock(return_value="Hello %name%")
        branding = BrandingConfig(display_name="Auth")
        html, text = renderer.render_email("test", {"name": "World"}, branding=branding)
        assert "World" in html
        assert "World" in text

    def test_no_mjml_returns_empty(self, renderer):
        renderer._get_compiled_html = MagicMock(return_value=None)
        renderer._load_txt = MagicMock(return_value=None)
        branding = BrandingConfig(display_name="Auth")
        html, text = renderer.render_email("missing", {}, branding=branding)
        assert html == ""
        assert text == ""

    def test_html_fallback_for_text(self, renderer):
        renderer._get_compiled_html = MagicMock(return_value="<p>Hello</p>")
        renderer._load_txt = MagicMock(return_value=None)
        renderer._html_to_plain_text = MagicMock(return_value="Hello")
        branding = BrandingConfig(display_name="Auth")
        html, text = renderer.render_email("test", {}, branding=branding)
        assert text == "Hello"

    def test_year_auto_injected(self, renderer):
        renderer._get_compiled_html = MagicMock(return_value="{{ year }}")
        renderer._load_txt = MagicMock(return_value=None)
        branding = BrandingConfig(display_name="Auth")
        html, _ = renderer.render_email("test", {}, branding=branding)
        assert html.isdigit()

    def test_display_name_fallback(self, renderer):
        renderer._get_compiled_html = MagicMock(return_value="{{ display_name }}")
        renderer._load_txt = MagicMock(return_value=None)
        branding = BrandingConfig(display_name="")
        html, _ = renderer.render_email("test", {}, branding=branding)
        # Should fall back display_name to "Auth"
        assert branding.display_name == "Auth"


# ── invalidate_tenant_cache ─────────────────────────────────────────────────


class TestInvalidateTenantCache:
    def test_removes_from_cache(self, renderer):
        renderer._tenant_cache[("t1", "password_reset")] = "<html>"
        renderer.invalidate_tenant_cache("t1", "emails/mjml/password_reset.mjml")
        assert ("t1", "password_reset") not in renderer._tenant_cache

    def test_short_name_without_prefix(self, renderer):
        renderer._tenant_cache[("t1", "test")] = "<html>"
        renderer.invalidate_tenant_cache("t1", "test")
        assert ("t1", "test") not in renderer._tenant_cache

    def test_noop_if_not_cached(self, renderer):
        renderer.invalidate_tenant_cache("t1", "missing")  # Should not raise


# ── render_email_for_tenant ─────────────────────────────────────────────────


class TestRenderEmailForTenant:
    @pytest.mark.asyncio
    async def test_no_tenant(self, db, renderer):
        renderer._get_compiled_html = MagicMock(return_value="<p>Hello</p>")
        renderer._load_txt = MagicMock(return_value=None)
        renderer._html_to_plain_text = MagicMock(return_value="Hello")
        branding = BrandingConfig(display_name="Auth")
        html, text = await renderer.render_email_for_tenant(db, "test", {}, branding=branding)
        assert "Hello" in html

    @pytest.mark.asyncio
    async def test_with_tenant_override(self, db, renderer):
        renderer._get_tenant_compiled_html = AsyncMock(return_value="<p>Tenant</p>")
        renderer._get_tenant_txt = AsyncMock(return_value=None)
        renderer._html_to_plain_text = MagicMock(return_value="Tenant")
        branding = BrandingConfig(display_name="Auth")
        html, text = await renderer.render_email_for_tenant(
            db, "test", {}, branding=branding, tenant_id="t1"
        )
        assert "Tenant" in html

    @pytest.mark.asyncio
    async def test_tenant_override_not_found_falls_back(self, db, renderer):
        renderer._get_tenant_compiled_html = AsyncMock(return_value=None)
        renderer._get_compiled_html = MagicMock(return_value="<p>Default</p>")
        renderer._get_tenant_txt = AsyncMock(return_value=None)
        renderer._load_txt = MagicMock(return_value=None)
        renderer._html_to_plain_text = MagicMock(return_value="Default")
        branding = BrandingConfig(display_name="Auth")
        html, text = await renderer.render_email_for_tenant(
            db, "test", {}, branding=branding, tenant_id="t1"
        )
        assert "Default" in html

    @pytest.mark.asyncio
    async def test_tenant_txt_override(self, db, renderer):
        renderer._get_tenant_compiled_html = AsyncMock(return_value=None)
        renderer._get_compiled_html = MagicMock(return_value="<p>HTML</p>")
        renderer._get_tenant_txt = AsyncMock(return_value="Custom %name% text")
        branding = BrandingConfig(display_name="Auth")
        html, text = await renderer.render_email_for_tenant(
            db, "test", {"name": "World"}, branding=branding, tenant_id="t1"
        )
        assert "World" in text


# ── _get_tenant_compiled_html ───────────────────────────────────────────────


def _make_tenant_template(content: str, is_active: bool = True) -> MagicMock:
    """Build a ``TenantTemplate``-like mock."""
    template = MagicMock()
    template.content = content
    template.is_active = is_active
    return template


class TestGetTenantCompiledHtml:
    @pytest.mark.asyncio
    async def test_cached(self, db, renderer):
        tenant_id = str(uuid.uuid4())
        renderer._tenant_cache[(tenant_id, "test")] = "<cached>"
        result = await renderer._get_tenant_compiled_html(db, tenant_id, "test")
        assert result == "<cached>"

    @pytest.mark.asyncio
    async def test_from_db(self, db, renderer):
        tenant_id = str(uuid.uuid4())
        template = _make_tenant_template("<mjml></mjml>")
        renderer._compile_mjml = MagicMock(return_value="<compiled>")

        with patch("auth.services.email_renderer.TenantService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_template = AsyncMock(return_value=template)
            result = await renderer._get_tenant_compiled_html(db, tenant_id, "test")

        assert result == "<compiled>"
        assert (tenant_id, "test") in renderer._tenant_cache

    @pytest.mark.asyncio
    async def test_not_found(self, db, renderer):
        tenant_id = str(uuid.uuid4())
        with patch("auth.services.email_renderer.TenantService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_template = AsyncMock(return_value=None)
            result = await renderer._get_tenant_compiled_html(db, tenant_id, "test")
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_template_treated_as_none(self, db, renderer):
        """An inactive tenant override is ignored (falls back to filesystem)."""
        tenant_id = str(uuid.uuid4())
        template = _make_tenant_template("<mjml></mjml>", is_active=False)
        with patch("auth.services.email_renderer.TenantService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_template = AsyncMock(return_value=template)
            result = await renderer._get_tenant_compiled_html(db, tenant_id, "test")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_tenant_id_returns_none(self, db, renderer):
        """Non-UUID tenant_id is handled gracefully."""
        result = await renderer._get_tenant_compiled_html(db, "not-a-uuid", "test")
        assert result is None

    @pytest.mark.asyncio
    async def test_compile_error_returns_none(self, db, renderer):
        tenant_id = str(uuid.uuid4())
        template = _make_tenant_template("<mjml>")
        renderer._compile_mjml = MagicMock(side_effect=Exception("compile fail"))

        with patch("auth.services.email_renderer.TenantService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_template = AsyncMock(return_value=template)
            result = await renderer._get_tenant_compiled_html(db, tenant_id, "test")
        assert result is None


# ── _get_tenant_txt ─────────────────────────────────────────────────────────


class TestGetTenantTxt:
    @pytest.mark.asyncio
    async def test_found(self, db, renderer):
        tenant_id = str(uuid.uuid4())
        template = _make_tenant_template("Custom text")
        with patch("auth.services.email_renderer.TenantService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_template = AsyncMock(return_value=template)
            result = await renderer._get_tenant_txt(db, tenant_id, "test")
        assert result == "Custom text"

    @pytest.mark.asyncio
    async def test_not_found(self, db, renderer):
        tenant_id = str(uuid.uuid4())
        with patch("auth.services.email_renderer.TenantService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_template = AsyncMock(return_value=None)
            result = await renderer._get_tenant_txt(db, tenant_id, "test")
        assert result is None

    @pytest.mark.asyncio
    async def test_error_returns_none(self, db, renderer):
        tenant_id = str(uuid.uuid4())
        with patch("auth.services.email_renderer.TenantService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_template = AsyncMock(side_effect=Exception("db error"))
            result = await renderer._get_tenant_txt(db, tenant_id, "test")
        assert result is None


# ── get_email_renderer ──────────────────────────────────────────────────────


class TestGetEmailRenderer:
    def test_singleton(self):
        r1 = get_email_renderer()
        r2 = get_email_renderer()
        assert r1 is r2

    def test_creates_new(self):
        r = get_email_renderer()
        assert isinstance(r, EmailRenderer)


# ── default branding / pre-set year ─────────────────────────────────────────


class TestRenderEmailDefaults:
    def test_branding_defaults_when_omitted(self, renderer):
        renderer._get_compiled_html = MagicMock(return_value="{{ display_name }}")
        renderer._load_txt = MagicMock(return_value=None)

        html, _ = renderer.render_email("test", {})

        assert html == "Auth"

    def test_explicit_year_is_not_overwritten(self, renderer):
        renderer._get_compiled_html = MagicMock(return_value="{{ year }}")
        renderer._load_txt = MagicMock(return_value=None)

        html, _ = renderer.render_email("test", {"year": 1999}, branding=BrandingConfig())

        assert html == "1999"


class TestRenderEmailForTenantDefaults:
    @pytest.mark.asyncio
    async def test_branding_defaults_when_omitted(self, db, renderer):
        renderer._get_compiled_html = MagicMock(return_value="{{ display_name }}")
        renderer._load_txt = MagicMock(return_value=None)

        html, _ = await renderer.render_email_for_tenant(db, "test", {})

        assert html == "Auth"

    @pytest.mark.asyncio
    async def test_explicit_year_is_not_overwritten(self, db, renderer):
        renderer._get_compiled_html = MagicMock(return_value="{{ year }}")
        renderer._load_txt = MagicMock(return_value=None)

        html, _ = await renderer.render_email_for_tenant(db, "test", {"year": 2001})

        assert html == "2001"

    @pytest.mark.asyncio
    async def test_no_template_anywhere_returns_empty_pair(self, db, renderer):
        renderer._get_tenant_compiled_html = AsyncMock(return_value=None)
        renderer._get_compiled_html = MagicMock(return_value=None)
        renderer._get_tenant_txt = AsyncMock(return_value=None)
        renderer._load_txt = MagicMock(return_value=None)

        html, text = await renderer.render_email_for_tenant(
            db, "missing", {}, branding=BrandingConfig(display_name="Auth"), tenant_id="t1"
        )

        assert html == ""
        assert text == ""
