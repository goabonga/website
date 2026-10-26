# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Jinja2 environment shared by the web pages.

The pages never carry values that belong to the deployment: the operator's name and
contact addresses, the public URL and the limits of the plans come from the settings and
from billing. This module gives the templates the ``site()`` function and the filters that
display the limits of a plan, whatever their names.
"""

from fastapi.templating import Jinja2Templates

from knowledge.config import TEMPLATES_DIR, docs_context, get_settings


def site() -> dict[str, str]:
    """Return the identity of the operator, as configured, for the templates.

    Every value is an empty string when it is not configured; the templates leave out
    what is empty.
    """
    settings = get_settings()
    return {
        "operator_name": settings.operator_name,
        "contact_email": settings.contact_email,
        "sales_email": settings.sales_email,
        "legal_email": settings.legal_email,
        "privacy_email": settings.privacy_email,
        "base_url": settings.app_base_url.rstrip("/"),
    }


def limit_label(name: str) -> str:
    """Make a limit name readable: ``max_total_documents`` becomes ``Total documents``."""
    words = name.removeprefix("max_").removesuffix("_bytes").replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else name


def format_limit(name: str, value: int | None) -> str:
    """Display the value of a limit: ``-1`` is unlimited, a ``*_bytes`` limit is a size."""
    if value is None:
        return "-"
    if value < 0:
        return "Unlimited"
    if name.endswith("_bytes"):
        size = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.0f} {unit}" if size == int(size) else f"{size:.1f} {unit}"
            size /= 1024
    return f"{value:,}"


def create_templates() -> Jinja2Templates:
    """Create the template engine of a router, with the shared globals and filters."""
    templates = Jinja2Templates(directory=TEMPLATES_DIR, context_processors=[docs_context])
    templates.env.globals["site"] = site
    templates.env.filters["limit_label"] = limit_label
    templates.env.globals["format_limit"] = format_limit
    return templates
