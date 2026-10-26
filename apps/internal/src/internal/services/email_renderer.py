# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email rendering service with MJML compilation and Jinja2 templating."""

import re
from typing import Any

from bs4 import BeautifulSoup
from jinja2 import BaseLoader, Environment

from internal.logging import get_logger

logger = get_logger(__name__)


class EmailRenderer:
    """Service for compiling MJML to HTML and rendering templates with variables."""

    # Default MJML template for new emails
    # Note: Use %variable% syntax to avoid conflicts with MRML's internal parser
    DEFAULT_MJML = """<mjml>
  <mj-head>
    <mj-title>%subject%</mj-title>
    <mj-preview>Preview text here</mj-preview>
  </mj-head>
  <mj-body background-color="#f4f4f4">
    <mj-section background-color="#ffffff" padding="20px">
      <mj-column>
        <mj-text font-size="24px" font-weight="bold" color="#1a1a2e" font-family="Arial, sans-serif">Hello %first_name%!</mj-text>
        <mj-text font-size="14px" color="#333333" line-height="1.5" font-family="Arial, sans-serif">Your email content goes here. You can use variables like %email% to personalize.</mj-text>
        <mj-button href="https://example.com" background-color="#e94560" border-radius="4px" font-family="Arial, sans-serif">Call to Action</mj-button>
      </mj-column>
    </mj-section>
    <mj-section padding="10px">
      <mj-column>
        <mj-text font-size="12px" color="#666666" align="center" font-family="Arial, sans-serif">2024 Your Company. All rights reserved.</mj-text>
      </mj-column>
    </mj-section>
  </mj-body>
</mjml>"""

    # Variable patterns:
    # - {{variable_name}} for Jinja2 rendering (final output)
    # - %variable_name% for MJML storage (avoids conflicts with MRML parser)
    JINJA_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")
    PERCENT_VAR_PATTERN = re.compile(r"%(\w+)%")

    def __init__(self):
        """Initialize the email renderer."""
        self._jinja_env = Environment(
            loader=BaseLoader(),
            autoescape=True,
            variable_start_string="{{",
            variable_end_string="}}",
        )

    def compile_mjml(self, mjml_source: str) -> tuple[str, list[str]]:
        """Compile MJML to HTML.

        MJML source should use %variable% syntax to avoid Mustache/Handlebars conflicts.
        The compiled HTML will have {{variable}} syntax for Jinja2 rendering.

        Args:
            mjml_source: MJML source code with %variable% placeholders

        Returns:
            Tuple of (compiled HTML, list of errors)
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
            html = self.PERCENT_VAR_PATTERN.sub(r"{{\1}}", html)

            return html, []

        except Exception as e:
            lines = mjml_source.split("\n")
            logger.error(
                "MJML compilation failed: %s | Total lines: %d | First 500 chars: %s",
                e,
                len(lines),
                mjml_source[:500].replace("\n", "\\n"),
            )
            return "", [str(e)]

    def extract_variables(self, mjml_source: str, subject: str = "") -> list[str]:
        """Extract variable names from MJML source and subject.

        Args:
            mjml_source: MJML source code (with %var% or {{var}} syntax)
            subject: Subject line template

        Returns:
            List of unique variable names found
        """
        combined_text = f"{subject}\n{mjml_source}"
        # Support both %var% and {{var}} syntax
        matches = self.PERCENT_VAR_PATTERN.findall(combined_text)
        matches += self.JINJA_VAR_PATTERN.findall(combined_text)
        # Return unique variables preserving order
        seen = set()
        unique = []
        for var in matches:
            if var not in seen:
                seen.add(var)
                unique.append(var)
        return unique

    def html_to_plain_text(self, html: str) -> str:
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

    def render_template(
        self,
        html: str,
        variables: dict[str, Any],
        subject: str = "",
    ) -> tuple[str, str]:
        """Render HTML template with variables.

        Args:
            html: HTML template with {{variable}} placeholders
            variables: Dictionary of variable values
            subject: Subject line template

        Returns:
            Tuple of (rendered HTML, rendered subject)
        """
        try:
            # Render HTML
            html_template = self._jinja_env.from_string(html)
            rendered_html = html_template.render(**variables)

            # Render subject
            subject_template = self._jinja_env.from_string(subject)
            rendered_subject = subject_template.render(**variables)

            return rendered_html, rendered_subject

        except Exception as e:
            logger.error("Template rendering failed: %s", e)
            return html, subject

    def get_default_mjml(self) -> str:
        """Get default MJML template for new emails."""
        return self.DEFAULT_MJML

    def validate_mjml(self, mjml_source: str) -> tuple[bool, list[str]]:
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

        # Try to compile to check for errors
        _, errors = self.compile_mjml(mjml_source)
        return len(errors) == 0, errors


# Singleton instance
_renderer: EmailRenderer | None = None


def get_email_renderer() -> EmailRenderer:
    """Get or create the email renderer singleton."""
    global _renderer
    if _renderer is None:
        _renderer = EmailRenderer()
    return _renderer
