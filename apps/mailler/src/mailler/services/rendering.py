# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Template rendering shared by the template API, campaigns and template sending.

Templates are written by the clients, so they are rendered in a Jinja2 sandbox:
a template cannot reach Python internals, the filesystem or the process. HTML
is rendered with auto-escaping, so variable values cannot inject markup; the
subject and the plain text version are not HTML and are rendered as they are.
"""

import re
from dataclasses import dataclass
from typing import Any

from jinja2 import Template, TemplateError, TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

# HTML body: values are escaped.
html_env = SandboxedEnvironment(autoescape=True)
# Subject and plain text: values are used as they are.
text_env = SandboxedEnvironment(autoescape=False)

# %name% but not %%name%% (escaped)
_PERCENT_VARIABLE = re.compile(r"(?<!%)%([a-zA-Z_][a-zA-Z0-9_]*)%(?!%)")


class RenderError(ValueError):
    """A template could not be rendered (syntax error, missing variable, forbidden construct)."""


@dataclass(frozen=True)
class RenderedEmail:
    """The three parts of a rendered template."""

    subject: str
    html: str
    plain_text: str | None


def convert_percent_syntax(text: str) -> str:
    """Convert the ``%variable%`` syntax of plain text templates to ``{{ variable }}``."""
    return _PERCENT_VARIABLE.sub(r"{{ \1 }}", text)


def html_template(source: str) -> Template:
    """Compile an HTML body template (auto-escaped)."""
    return html_env.from_string(source)


def text_template(source: str, *, percent_syntax: bool = False) -> Template:
    """Compile a subject or plain text template (not escaped)."""
    return text_env.from_string(convert_percent_syntax(source) if percent_syntax else source)


def _describe(error: TemplateError) -> str:
    if isinstance(error, TemplateSyntaxError):
        return f"Template syntax error: {error}"
    if isinstance(error, UndefinedError):
        return f"Missing variable: {error}"
    if isinstance(error, SecurityError):
        return f"Template not allowed: {error}"
    return f"Template error: {error}"


def render_parts(
    *,
    subject_template: str,
    html_compiled: str,
    plain_text: str | None,
    variables: dict[str, Any],
) -> RenderedEmail:
    """Render the subject, the HTML body and the optional plain text of a template.

    A variable that is not provided renders as an empty string; operations on
    it (attribute access on nothing, for example) raise.

    Raises:
        RenderError: On a syntax error, a failing expression or a forbidden construct.
    """
    try:
        subject = text_template(subject_template).render(variables)
        html = html_template(html_compiled).render(variables)
        text = (
            text_template(plain_text, percent_syntax=True).render(variables) if plain_text else None
        )
    except TemplateError as error:
        raise RenderError(_describe(error)) from error
    return RenderedEmail(subject=subject, html=html, plain_text=text)
