# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Compile MJML email templates and send via mailler."""

import re
from pathlib import Path

import mrml

from apt_server.config import settings
from apt_server.logging import get_logger
from apt_server.services import mailler

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"

_compiled_cache: dict[str, str] = {}


def _compile_mjml(template_name: str) -> str:
    """Compile an MJML template to HTML, caching the result."""
    if template_name in _compiled_cache:
        return _compiled_cache[template_name]

    path = TEMPLATES_DIR / f"{template_name}.mjml"
    if not path.exists():
        raise FileNotFoundError(f"email template not found: {path}")

    mjml_source = path.read_text()
    html = mrml.to_html(mjml_source).content
    # Convert %variable% placeholders to Jinja2 {{variable}}
    html = re.sub(r"%(\w+)%", r"{{\1}}", html)
    _compiled_cache[template_name] = html
    return html


def render(template_name: str, **variables: str) -> str:
    """Render an email template with variables."""
    from jinja2 import Template

    html = _compile_mjml(template_name)
    return Template(html).render(**variables)


async def send_package_shared(
    *,
    to_email: str,
    to_name: str,
    sharer: str,
    role: str,
    package_name: str,
    package_version: str,
    package_arch: str,
    package_component: str,
    package_url: str,
) -> None:
    """Send a 'package shared with you' notification email."""
    if settings.email_backend.lower() != "mailler":
        logger.debug("email disabled, skipping share notification to %s", to_email)
        return

    html = render(
        "package_shared",
        app_name=settings.app_name,
        sharer=sharer,
        role=role,
        package_name=package_name,
        package_version=package_version,
        package_arch=package_arch,
        package_component=package_component,
        package_url=package_url,
    )

    await mailler.send_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"{sharer} shared {package_name} {package_version} with you",
        html_content=html,
    )
