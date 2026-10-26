# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant branding and theming service."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from jinja2 import BaseLoader, Environment, TemplateNotFound
from markupsafe import Markup
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.tenant import Tenant, TenantBranding, TenantTemplate
from auth.db.repositories.branding import BrandingRepository
from auth.middlewares.tenant import get_tenant_context

logger = logging.getLogger(__name__)


@dataclass
class BrandingConfig:
    """Branding configuration for rendering templates.

    Contains all theming variables and custom CSS for a tenant.
    Falls back to defaults when no tenant branding is configured.
    """

    # Tenant info
    tenant_id: "UUID | None" = None
    tenant_slug: str = ""
    display_name: str = ""

    # Logo and favicon
    logo_url: str | None = None
    logo_dark_url: str | None = None
    favicon_url: str | None = None

    # Colors (Admin dark theme by default)
    primary_color: str = "#e94560"
    secondary_color: str = "#0f3460"
    accent_color: str = "#e94560"
    background_color: str = "#1a1a2e"
    surface_color: str = "#16213e"
    text_color: str = "#e0e0e0"
    text_muted_color: str = "#a0a0a0"
    error_color: str = "#ff6b6b"
    success_color: str = "#00b894"
    border_color: str = "#0f3460"
    warning_color: str = "#fdcb6e"
    info_color: str = "#74b9ff"

    # Input-specific colors (None = fallback to generic colors in CSS)
    input_background_color: str | None = None
    input_focus_background_color: str | None = None
    input_border_color: str | None = None
    input_focus_border_color: str | None = None
    input_text_color: str | None = None

    # Typography
    font_family: str = (
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif"
    )
    font_url: str | None = None

    # Custom CSS/JS
    custom_css: str = ""
    custom_js: str = ""

    # Settings
    show_powered_by: bool = True

    @classmethod
    def from_tenant(cls, tenant: Tenant | None) -> "BrandingConfig":
        """Create branding config from a tenant and its branding relation."""
        if not tenant:
            return cls()

        branding = tenant.branding

        config = cls(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            display_name=tenant.display_name,
        )

        if branding:
            config.logo_url = branding.logo_url
            config.logo_dark_url = branding.logo_dark_url
            config.favicon_url = branding.favicon_url
            config.primary_color = branding.primary_color
            config.secondary_color = branding.secondary_color
            config.accent_color = branding.accent_color
            config.background_color = branding.background_color
            config.surface_color = branding.surface_color
            config.text_color = branding.text_color
            config.text_muted_color = branding.text_muted_color
            config.error_color = branding.error_color
            config.success_color = branding.success_color
            config.border_color = branding.border_color
            config.warning_color = branding.warning_color
            config.info_color = branding.info_color
            config.input_background_color = branding.input_background_color
            config.input_focus_background_color = branding.input_focus_background_color
            config.input_border_color = branding.input_border_color
            config.input_focus_border_color = branding.input_focus_border_color
            config.input_text_color = branding.input_text_color
            config.font_family = branding.font_family
            config.font_url = branding.font_url
            config.custom_css = branding.custom_css or ""
            config.custom_js = branding.custom_js or ""
            config.show_powered_by = branding.show_powered_by

        return config

    def to_css_variables(self) -> str:
        """Generate CSS custom properties from branding config."""
        focus_bg = (
            self.input_focus_background_color
            or self.input_background_color
            or self.background_color
        )
        return f""":root {{
    --primary-color: {self.primary_color};
    --secondary-color: {self.secondary_color};
    --accent-color: {self.accent_color};
    --background-color: {self.background_color};
    --surface-color: {self.surface_color};
    --text-color: {self.text_color};
    --text-muted-color: {self.text_muted_color};
    --error-color: {self.error_color};
    --success-color: {self.success_color};
    --border-color: {self.border_color};
    --warning-color: {self.warning_color};
    --info-color: {self.info_color};
    --input-bg-color: {self.input_background_color or self.background_color};
    --input-focus-bg-color: {focus_bg};
    --input-border-color: {self.input_border_color or self.border_color};
    --input-focus-border-color: {self.input_focus_border_color or self.primary_color};
    --input-text-color: {self.input_text_color or self.text_color};
    --font-family: {self.font_family};
}}"""

    def get_font_import(self) -> str:
        """Generate font import CSS if a custom font URL is specified."""
        if self.font_url:
            return f'@import url("{self.font_url}");'
        return ""


class TenantTemplateLoader(BaseLoader):
    """Jinja2 template loader that loads templates from database first, then filesystem.

    This loader checks if a tenant has a custom template in the database.
    If not found, it falls back to the default templates on the filesystem.
    """

    def __init__(
        self,
        base_path: Path,
        db_session_factory,
        repository: BrandingRepository | None = None,
    ):
        """Initialize the loader.

        Args:
            base_path: Path to the default templates directory.
            db_session_factory: Async session factory for database access.
            repository: Optional :class:`BrandingRepository` override (for tests).
        """
        self.base_path = base_path
        self.db_session_factory = db_session_factory
        self._repo = repository or BrandingRepository()
        self._cache: dict[tuple[str, str], tuple[str, float]] = {}

    def get_source(self, _environment: Environment, template: str):
        """Load template source.

        This is called synchronously by Jinja2, but we need async DB access.
        For the sync case, we only check filesystem. Use get_source_async for DB templates.
        """
        # For sync access, only use filesystem
        template_path = self.base_path / template
        if template_path.exists():
            source = template_path.read_text(encoding="utf-8")
            mtime = template_path.stat().st_mtime
            return source, str(template_path), lambda: template_path.stat().st_mtime == mtime

        raise TemplateNotFound(template)

    async def get_source_async(
        self,
        db: AsyncSession,
        template: str,
        tenant_id: "UUID | None" = None,
    ) -> tuple[str, str | None, bool]:
        """Load template source asynchronously, checking database first.

        Args:
            db: Database session.
            template: Template name (e.g., "auth/login.html").
            tenant_id: Optional tenant ID to check for custom templates.

        Returns:
            Tuple of (source, filename, is_from_db).
        """
        # Check database for tenant-specific template
        if tenant_id:
            db_template = await self._repo.find_active_template(db, tenant_id, template)

            if db_template:
                logger.debug(
                    "Using database template for tenant %s: %s",
                    tenant_id,
                    template,
                )
                return db_template.content, None, True

        # Fall back to filesystem
        template_path = self.base_path / template
        if template_path.exists():
            source = template_path.read_text(encoding="utf-8")
            return source, str(template_path), False

        raise TemplateNotFound(template)


class BrandingService:
    """Service for managing tenant branding and themed template rendering."""

    # Templates that can be customized per tenant
    CUSTOMIZABLE_TEMPLATES = [
        "base.html",
        "auth/login.html",
        "auth/register.html",
        "auth/forgot_password.html",
        "auth/reset_password.html",
        "auth/verify_email.html",
        "auth/mfa_setup.html",
        "auth/mfa_email.html",
        "oauth2/consent.html",
        "oauth2/device.html",
        "oauth2/device_consent.html",
        "oauth2/device_complete.html",
        "oauth2/error.html",
        "emails/mjml/password_reset.mjml",
        "emails/mjml/email_verification.mjml",
        "emails/mjml/mfa_code.mjml",
        "auth/settings/base.html",
        "auth/settings/profile.html",
        "auth/settings/password.html",
        "auth/settings/security.html",
        "auth/settings/sessions.html",
        "auth/settings/applications.html",
        "auth/settings/emails.html",
        "auth/settings/tokens.html",
        "auth/settings/tenants.html",
    ]

    def __init__(
        self,
        templates_path: Path,
        db_session_factory,
        repository: BrandingRepository | None = None,
    ):
        """Initialize the branding service.

        Args:
            templates_path: Path to the default templates directory.
            db_session_factory: Async session factory for database access.
            repository: Optional :class:`BrandingRepository` override.
        """
        self.templates_path = templates_path
        self.db_session_factory = db_session_factory
        self._repo = repository or BrandingRepository()
        self.loader = TenantTemplateLoader(
            templates_path, db_session_factory, repository=self._repo
        )
        self._env = Environment(
            loader=self.loader,
            autoescape=True,
            enable_async=True,
        )
        self._env.filters["tojson"] = lambda v: Markup(  # nosec B704
            json.dumps(v, default=str)
        )

    async def get_branding(
        self, db: AsyncSession, tenant_id: "UUID | None" = None
    ) -> BrandingConfig:
        """Get branding configuration for a tenant.

        Args:
            db: Database session.
            tenant_id: Optional tenant ID. If None, returns default branding.

        Returns:
            BrandingConfig with tenant's branding or defaults.
        """
        if not tenant_id:
            return BrandingConfig()

        tenant = await self._repo.find_tenant_with_branding(db, tenant_id)

        return BrandingConfig.from_tenant(tenant)

    async def get_branding_record(
        self, db: AsyncSession, tenant_id: "UUID"
    ) -> TenantBranding | None:
        """Get the raw ``TenantBranding`` record for a tenant.

        Unlike :meth:`get_branding` which returns a :class:`BrandingConfig`
        (merged with defaults), this returns the persisted model or ``None``
        when no custom branding has been saved yet.

        Args:
            db: Database session.
            tenant_id: Tenant ID.

        Returns:
            TenantBranding model or None if not configured.
        """
        return await self._repo.find_branding(db, tenant_id)

    async def get_branding_for_current_tenant(self, db: AsyncSession) -> BrandingConfig:
        """Get branding for the current tenant from context.

        Args:
            db: Database session.

        Returns:
            BrandingConfig for the current tenant or defaults.
        """
        tenant_ctx = get_tenant_context()
        tenant_id_value = tenant_ctx.tenant_id if tenant_ctx else None
        if isinstance(tenant_id_value, UUID):
            tenant_id = tenant_id_value
        elif tenant_id_value:
            try:
                tenant_id = UUID(str(tenant_id_value))
            except (ValueError, TypeError, AttributeError):
                tenant_id = None
        else:
            tenant_id = None
        return await self.get_branding(db, tenant_id)

    async def render_template(
        self,
        db: AsyncSession,
        template_name: str,
        context: dict,
        tenant_id: "UUID | None" = None,
    ) -> str:
        """Render a template with tenant-specific customization.

        Args:
            db: Database session.
            template_name: Name of the template to render.
            context: Template context variables.
            tenant_id: Optional tenant ID for custom templates.

        Returns:
            Rendered HTML string.
        """
        # Get template source (DB or filesystem)
        source, filename, is_from_db = await self.loader.get_source_async(
            db, template_name, tenant_id
        )

        # Compile and render
        template = self._env.from_string(source)

        # Add branding to context
        if "branding" not in context:
            branding = await self.get_branding(db, tenant_id)
            context["branding"] = branding

        return await template.render_async(**context)

    async def get_tenant_templates(
        self,
        db: AsyncSession,
        tenant_id: "UUID",
    ) -> list[TenantTemplate]:
        """Get all custom templates for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant ID.

        Returns:
            List of TenantTemplate objects.
        """
        return await self._repo.list_templates(db, tenant_id)

    async def get_template(
        self,
        db: AsyncSession,
        tenant_id: "UUID",
        template_name: str,
    ) -> TenantTemplate | None:
        """Get a specific custom template for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant ID.
            template_name: Template name.

        Returns:
            TenantTemplate or None if not found.
        """
        return await self._repo.find_template(db, tenant_id, template_name)

    async def save_template(
        self,
        db: AsyncSession,
        tenant_id: "UUID",
        template_name: str,
        content: str,
        description: str | None = None,
        is_active: bool = True,
    ) -> TenantTemplate:
        """Save or update a custom template for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant ID.
            template_name: Template name.
            content: Jinja2 template content.
            description: Optional description.
            is_active: Whether the template is active.

        Returns:
            Created or updated TenantTemplate.
        """
        existing = await self.get_template(db, tenant_id, template_name)

        if existing:
            existing.content = content
            existing.description = description
            existing.is_active = is_active
            await self._repo.flush(db)
            return existing

        template = TenantTemplate(
            tenant_id=tenant_id,
            template_name=template_name,
            content=content,
            description=description,
            is_active=is_active,
        )
        await self._repo.add(db, template)
        return template

    async def delete_template(
        self,
        db: AsyncSession,
        tenant_id: "UUID",
        template_name: str,
    ) -> bool:
        """Delete a custom template for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant ID.
            template_name: Template name.

        Returns:
            True if deleted, False if not found.
        """
        template = await self.get_template(db, tenant_id, template_name)
        if template:
            await self._repo.delete(db, template)
            return True
        return False

    async def get_default_template_content(self, template_name: str) -> str | None:
        """Get the default template content from filesystem.

        Args:
            template_name: Template name.

        Returns:
            Template content or None if not found.
        """
        template_path = self.templates_path / template_name
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return None

    async def save_branding(
        self,
        db: AsyncSession,
        tenant_id: "UUID",
        **kwargs,
    ) -> TenantBranding:
        """Save or update branding for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant ID.
            **kwargs: Branding fields to update.

        Returns:
            Created or updated TenantBranding.
        """
        branding = await self._repo.find_branding(db, tenant_id)

        if branding:
            for key, value in kwargs.items():
                if hasattr(branding, key):
                    setattr(branding, key, value)
            await self._repo.flush(db)
            return branding

        branding = TenantBranding(tenant_id=tenant_id, **kwargs)
        await self._repo.add(db, branding)
        return branding

    async def delete_branding(self, db: AsyncSession, tenant_id: "UUID") -> bool:
        """Delete branding for a tenant (resets to defaults).

        Args:
            db: Database session.
            tenant_id: Tenant ID.

        Returns:
            True if deleted, False if not found.
        """
        branding = await self._repo.find_branding(db, tenant_id)
        if branding:
            await self._repo.delete(db, branding)
            return True
        return False
