# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MJML compilation service."""

import re
from typing import Any

from bs4 import BeautifulSoup

from mailler.logging import get_logger

logger = get_logger(__name__)

# Variable patterns:
# - {{variable_name}} for Jinja2 rendering (final output)
# - %variable_name% for MJML storage (avoids conflicts with MRML parser)
JINJA_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")
PERCENT_VAR_PATTERN = re.compile(r"%(\w+)%")


async def compile_mjml(mjml_source: str) -> dict[str, Any]:
    """Compile MJML to HTML.

    MJML source should use %variable% syntax to avoid Mustache/Handlebars conflicts.
    The compiled HTML will have {{variable}} syntax for Jinja2 rendering.

    Args:
        mjml_source: MJML source code with %variable% placeholders

    Returns:
        Dict with 'html' (compiled HTML) and 'errors' (list of error messages)
    """
    try:
        import mrml

        # Normalize line endings (Windows \r\n to Unix \n) - mrml doesn't handle \r\n
        mjml_source = mjml_source.replace("\r\n", "\n").replace("\r", "\n")

        logger.debug("MJML compilation | length=%d", len(mjml_source))

        # Compile MJML to HTML using mrml (direct Rust bindings)
        # mrml.to_html() returns an Output object, access .content for HTML string
        result = mrml.to_html(mjml_source)
        html = result.content

        # Convert %variable% to {{variable}} for Jinja2 rendering
        html = PERCENT_VAR_PATTERN.sub(r"{{\1}}", html)

        return {"html": html, "errors": None}

    except Exception as e:
        lines = mjml_source.split("\n")
        logger.error(
            "MJML compilation failed: %s | Total lines: %d | First 500 chars: %s",
            e,
            len(lines),
            mjml_source[:500].replace("\n", "\\n"),
        )
        return {"html": "", "errors": [str(e)]}


def extract_variables(mjml_source: str, subject: str = "") -> list[str]:
    """Extract variable names from MJML source and subject.

    Args:
        mjml_source: MJML source code (with %var% or {{var}} syntax)
        subject: Subject line template

    Returns:
        List of unique variable names found
    """
    combined_text = f"{subject}\n{mjml_source}"
    # Support both %var% and {{var}} syntax
    matches = PERCENT_VAR_PATTERN.findall(combined_text)
    matches += JINJA_VAR_PATTERN.findall(combined_text)
    # Return unique variables preserving order
    seen = set()
    unique = []
    for var in matches:
        if var not in seen:
            seen.add(var)
            unique.append(var)
    return unique


def html_to_plain_text(html: str) -> str:
    """Convert HTML to plain text for email fallback.

    Args:
        html: HTML content

    Returns:
        Plain text version
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    except Exception as e:
        logger.error("HTML to plain text conversion failed: %s", e)
        return ""


def validate_mjml(mjml_source: str) -> tuple[bool, list[str]]:
    """Validate MJML source without full compilation.

    Args:
        mjml_source: MJML source code

    Returns:
        Tuple of (is_valid, error_messages)
    """
    if not mjml_source.strip():
        return False, ["MJML source is empty"]

    if "<mjml>" not in mjml_source:
        return False, ["Missing <mjml> root element"]

    if "</mjml>" not in mjml_source:
        return False, ["Missing </mjml> closing tag"]

    return True, []
