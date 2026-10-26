# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email rendering service with MJML compilation and Jinja2 templating."""

import logging
import re
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import BaseLoader, Environment

from auth.services.tenant import TenantService

if TYPE_CHECKING:
    from auth.services.branding import BrandingConfig

logger = logging.getLogger(__name__)

# Template directories
_BASE_DIR = Path(__file__).parent.parent / "templates" / "emails"
MJML_DIR = _BASE_DIR / "mjml"
TXT_DIR = _BASE_DIR / "txt"

# BrandingConfig fields to inject into templates
BRANDING_FIELDS = {
    "primary_color",
    "secondary_color",
    "accent_color",
    "background_color",
    "surface_color",
    "text_color",
    "text_muted_color",
    "error_color",
    "success_color",
    "border_color",
    "warning_color",
    "info_color",
    "font_family",
    "display_name",
    "logo_url",
}


class EmailRenderer:
    """Service for compiling MJML to HTML and rendering email templates.

    Uses %variable% syntax in MJML sources to avoid conflicts with the MJML parser.
    After compilation, %var% is converted to {{var}} for Jinja2 rendering.
    """

    PERCENT_VAR_PATTERN = re.compile(r"%(\w+)%")

    def __init__(self) -> None:
        self._jinja_env = Environment(  # nosec B701 — email templates use raw HTML/MJML
            loader=BaseLoader(),
            autoescape=False,
        )
        self._compiled_cache: dict[str, str] = {}
        # Tenant-specific compiled MJML cache: (tenant_id, template_name) -> html
        self._tenant_cache: dict[tuple[str, str], str] = {}

    def _load_mjml(self, template_name: str) -> str | None:
        """Load raw MJML source from disk."""
        path = MJML_DIR / f"{template_name}.mjml"
        if not path.exists():
            logger.error("MJML template not found: %s", path)
            return None
        return path.read_text(encoding="utf-8")

    def _load_txt(self, template_name: str) -> str | None:
        """Load plain text template from disk."""
        path = TXT_DIR / f"{template_name}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def _compile_mjml(self, mjml_source: str) -> str:
        """Compile MJML to HTML via mrml, converting %var% to {{var}}."""
        import mrml

        mjml_source = mjml_source.replace("\r\n", "\n").replace("\r", "\n")
        result = mrml.to_html(mjml_source)
        html = result.content
        # Convert %variable% placeholders to {{variable}} for Jinja2
        html = self.PERCENT_VAR_PATTERN.sub(r"{{\1}}", html)
        return html

    def _get_compiled_html(self, template_name: str) -> str | None:
        """Get compiled HTML for a template, using cache."""
        if template_name in self._compiled_cache:
            return self._compiled_cache[template_name]

        mjml_source = self._load_mjml(template_name)
        if not mjml_source:
            return None

        try:
            html = self._compile_mjml(mjml_source)
            self._compiled_cache[template_name] = html
            return html
        except Exception as e:
            logger.error("MJML compilation failed for '%s': %s", template_name, e)
            return None

    def _render_jinja(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template string with variables."""
        template = self._jinja_env.from_string(template_str)
        return template.render(**variables)

    def _html_to_plain_text(self, html: str) -> str:
        """Fallback: convert HTML to plain text using BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
            lines = (line.strip() for line in text.splitlines())
            return "\n".join(chunk for chunk in lines if chunk)
        except Exception as e:
            logger.error("HTML to plain text conversion failed: %s", e)
            return ""

    def render_email(
        self,
        template_name: str,
        variables: dict[str, Any],
        branding: "BrandingConfig | None" = None,
    ) -> tuple[str, str]:
        """Render an email template returning (html, plain_text).

        Merges branding colors into template variables, compiles MJML to HTML,
        renders with Jinja2, and loads/renders plain text template.

        Args:
            template_name: Template name without extension (e.g., "password_reset").
            variables: Content-specific variables (reset_url, code, etc.).
            branding: Optional BrandingConfig. Defaults are used if None.

        Returns:
            Tuple of (rendered_html, rendered_plain_text).
        """
        from auth.services.branding import BrandingConfig

        if branding is None:
            branding = BrandingConfig()

        # Auto-inject year
        if "year" not in variables:
            variables["year"] = datetime.now(UTC).year

        # Default display_name fallback
        if not branding.display_name:
            branding.display_name = "Auth"

        # Merge branding fields into variables (content vars take precedence)
        branding_dict = asdict(branding)
        merged = {k: v for k, v in branding_dict.items() if k in BRANDING_FIELDS and v is not None}
        merged.update(variables)

        # Render HTML from MJML
        compiled_html = self._get_compiled_html(template_name)
        if compiled_html:
            rendered_html = self._render_jinja(compiled_html, merged)
        else:
            logger.error("No MJML template for '%s', returning empty HTML", template_name)
            rendered_html = ""

        # Render plain text (explicit template preferred, fallback to HTML stripping)
        txt_source = self._load_txt(template_name)
        if txt_source:
            txt_jinja = self.PERCENT_VAR_PATTERN.sub(r"{{\1}}", txt_source)
            rendered_text = self._render_jinja(txt_jinja, merged)
        elif rendered_html:
            rendered_text = self._html_to_plain_text(rendered_html)
        else:
            rendered_text = ""

        return rendered_html, rendered_text

    def invalidate_tenant_cache(self, tenant_id: str, template_name: str) -> None:
        """Remove a tenant-specific compiled template from cache."""
        # template_name from CUSTOMIZABLE_TEMPLATES is like "emails/mjml/password_reset.mjml"
        # Derive the short name used as cache key
        short_name = template_name
        if short_name.startswith("emails/mjml/"):
            short_name = short_name[len("emails/mjml/") :]
        if short_name.endswith(".mjml"):
            short_name = short_name[:-5]
        self._tenant_cache.pop((tenant_id, short_name), None)
        logger.debug("Invalidated tenant email cache: tenant=%s template=%s", tenant_id, short_name)

    async def render_email_for_tenant(
        self,
        db: Any,
        template_name: str,
        variables: dict[str, Any],
        branding: "BrandingConfig | None" = None,
        tenant_id: str | None = None,
    ) -> tuple[str, str]:
        """Render an email with tenant-specific template overrides.

        Checks the database for a tenant-specific MJML override before
        falling back to the filesystem default.

        Args:
            db: AsyncSession for database queries.
            template_name: Template name without extension (e.g., "password_reset").
            variables: Content-specific variables.
            branding: Optional BrandingConfig.
            tenant_id: Tenant UUID string. If None, uses filesystem default.

        Returns:
            Tuple of (rendered_html, rendered_plain_text).
        """
        from auth.services.branding import BrandingConfig

        if branding is None:
            branding = BrandingConfig()

        if "year" not in variables:
            variables["year"] = datetime.now(UTC).year

        if not branding.display_name:
            branding.display_name = "Auth"

        branding_dict = asdict(branding)
        merged = {k: v for k, v in branding_dict.items() if k in BRANDING_FIELDS and v is not None}
        merged.update(variables)

        compiled_html = None
        if tenant_id:
            compiled_html = await self._get_tenant_compiled_html(db, tenant_id, template_name)

        if compiled_html is None:
            compiled_html = self._get_compiled_html(template_name)

        if compiled_html:
            rendered_html = self._render_jinja(compiled_html, merged)
        else:
            logger.error("No MJML template for '%s', returning empty HTML", template_name)
            rendered_html = ""

        # Plain text: check for tenant override of .txt too (stored as emails/txt/<name>.txt)
        txt_source = None
        if tenant_id:
            txt_source = await self._get_tenant_txt(db, tenant_id, template_name)
        if txt_source is None:
            txt_source = self._load_txt(template_name)

        if txt_source:
            txt_jinja = self.PERCENT_VAR_PATTERN.sub(r"{{\1}}", txt_source)
            rendered_text = self._render_jinja(txt_jinja, merged)
        elif rendered_html:
            rendered_text = self._html_to_plain_text(rendered_html)
        else:
            rendered_text = ""

        return rendered_html, rendered_text

    async def _fetch_tenant_template_content(
        self, db: Any, tenant_id: str, template_name: str
    ) -> str | None:
        """Fetch the active :class:`TenantTemplate.content` via :class:`TenantService`.

        Returns ``None`` when the tenant has no override or the override row
        is inactive. ``tenant_id`` may be a UUID or a string.
        """
        try:
            tenant_uuid = (
                tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
            )
        except (TypeError, ValueError):
            return None

        tenant_service = TenantService()
        template = await tenant_service.get_template(db, tenant_uuid, template_name)
        if template is None or not template.is_active:
            return None
        return template.content

    async def _get_tenant_compiled_html(
        self, db: Any, tenant_id: str, template_name: str
    ) -> str | None:
        """Check DB for tenant MJML override (via :class:`TenantService`) and compile it."""
        cache_key = (tenant_id, template_name)
        if cache_key in self._tenant_cache:
            return self._tenant_cache[cache_key]

        try:
            db_template_name = f"emails/mjml/{template_name}.mjml"
            content = await self._fetch_tenant_template_content(db, tenant_id, db_template_name)
            if not content:
                return None

            html = self._compile_mjml(content)
            self._tenant_cache[cache_key] = html
            return html
        except Exception as e:
            logger.warning(
                "Failed to compile tenant MJML override "
                "(tenant=%s, template=%s): %s. "
                "Falling back to default.",
                tenant_id,
                template_name,
                e,
            )
            return None

    async def _get_tenant_txt(self, db: Any, tenant_id: str, template_name: str) -> str | None:
        """Check DB for tenant plain text email override via :class:`TenantService`."""
        try:
            db_template_name = f"emails/txt/{template_name}.txt"
            content = await self._fetch_tenant_template_content(db, tenant_id, db_template_name)
            return content if content else None
        except Exception as e:
            logger.warning(
                "Failed to load tenant TXT override (tenant=%s, template=%s): %s",
                tenant_id,
                template_name,
                e,
            )
            return None


# Singleton
_renderer: EmailRenderer | None = None


def get_email_renderer() -> EmailRenderer:
    """Get or create the email renderer singleton."""
    global _renderer
    if _renderer is None:
        _renderer = EmailRenderer()
    return _renderer
