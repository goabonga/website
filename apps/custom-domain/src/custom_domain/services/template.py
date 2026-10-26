# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Template rendering service."""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.config import settings
from custom_domain.logging import get_logger
from custom_domain.models.template import NginxTemplate
from custom_domain.services.privileged import run_privileged, stage_file

logger = get_logger(__name__)


@dataclass
class TemplateValidationResult:
    """Result of template validation."""

    valid: bool
    errors: list[str]
    rendered_output: str | None = None


class TemplateService:
    """Service for managing and rendering Jinja2 templates."""

    def __init__(self):
        templates_path = Path(settings.base_dir) / settings.templates_dir
        self.jinja_env = Environment(  # nosec B701 - nginx config templates, not HTML
            loader=FileSystemLoader(str(templates_path)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.default_http_template = "nginx_http.conf.j2"
        self.default_https_template = "nginx_https.conf.j2"

    async def get_template(
        self,
        db: AsyncSession,
        template_id: int | None = None,
    ) -> NginxTemplate | None:
        """Get a template by ID or the default template.

        Args:
            db: Database session
            template_id: Optional template ID

        Returns:
            NginxTemplate if found, None otherwise
        """
        if template_id:
            result = await db.execute(select(NginxTemplate).where(NginxTemplate.id == template_id))
            return result.scalar_one_or_none()

        # Get default template
        result = await db.execute(
            select(NginxTemplate).where(
                NginxTemplate.is_default == True,  # noqa: E712
                NginxTemplate.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    def render_template(
        self,
        template_source: str,
        context: dict,
    ) -> str:
        """Render a Jinja2 template from source string.

        Args:
            template_source: Template source code
            context: Template context variables

        Returns:
            Rendered template string
        """
        from jinja2 import Template

        template = Template(template_source)
        return template.render(**context)

    def render_default_http(self, context: dict) -> str:
        """Render the default HTTP template.

        Args:
            context: Template context variables

        Returns:
            Rendered template string
        """
        template = self.jinja_env.get_template(self.default_http_template)
        return template.render(**context)

    def render_default_https(self, context: dict) -> str:
        """Render the default HTTPS template.

        Args:
            context: Template context variables

        Returns:
            Rendered template string
        """
        template = self.jinja_env.get_template(self.default_https_template)
        return template.render(**context)

    def validate_template(
        self,
        template_source: str,
        test_context: dict | None = None,
    ) -> TemplateValidationResult:
        """Validate a Jinja2 template.

        Args:
            template_source: Template source code to validate
            test_context: Optional test context for rendering

        Returns:
            TemplateValidationResult with validation status
        """
        errors: list[str] = []
        rendered_output = None

        try:
            from jinja2 import Template

            template = Template(template_source)

            if test_context:
                try:
                    rendered_output = template.render(**test_context)
                except Exception as e:
                    errors.append(f"Render error: {e}")

        except TemplateSyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.message}")
        except Exception as e:
            errors.append(f"Template error: {e}")

        return TemplateValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            rendered_output=rendered_output,
        )

    async def validate_nginx_syntax(self, config: str) -> tuple[bool, str]:
        """Validate nginx configuration syntax through the privileged helper.

        The text is staged and the helper wraps it in the contexts nginx needs to
        test a virtual host alone. This runs where the helper can be started, that
        is in a worker, not in the API process.

        Args:
            config: Nginx configuration to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        staged = None
        try:
            token = uuid4().hex
            staged = stage_file(f"validate-{token}.conf", config)
            result = await run_privileged("check-snippet", token)
            if not result.ok:
                return False, result.stderr or "Unknown error"
            return True, ""
        except Exception as e:
            logger.warning("Nginx syntax validation failed: %s", e)
            return False, str(e)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)


template_service = TemplateService()
