# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Structural checks of the Jinja templates.

A browser repairs invalid markup silently, so these defects only show on a real page:

- a ``<form>`` inside another one is dropped by the HTML parser and its button submits the
  outer form (a "Delete" button of an edit page would save the page instead);
- a value interpolated in an inline event handler is a JavaScript string: a quote in a name
  ends it (and starts a script of the attacker's choice), unless it goes through ``tojson``.
"""

import re
from pathlib import Path

import pytest
from internal import TEMPLATES_DIR

TEMPLATES = sorted(Path(TEMPLATES_DIR).rglob("*.html"))

FORM_TAG = re.compile(r"<form\b[^>]*>|</form\s*>", re.IGNORECASE)
#: The value of an inline handler attribute (onclick, onsubmit, ...), double or single quoted.
HANDLER = re.compile(r"""\bon[a-z]+\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
EXPRESSION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
#: Interpolations that cannot hold a quote: identifiers and counters of the services.
SAFE_VALUE = re.compile(r"(^|[.\s])(id|version|member_count|total_recipients)\b|\|\s*length\b")


def _name(path: Path) -> str:
    return path.relative_to(TEMPLATES_DIR).as_posix()


def test_the_templates_are_found():
    assert TEMPLATES, f"no template under {TEMPLATES_DIR}"


@pytest.mark.parametrize("path", TEMPLATES, ids=_name)
def test_no_form_is_nested_in_another_form(path):
    depth = 0
    for match in FORM_TAG.finditer(path.read_text()):
        if match.group().startswith("</"):
            depth -= 1
            continue
        depth += 1
        line = path.read_text()[: match.start()].count("\n") + 1
        assert depth == 1, f"{_name(path)}:{line}: a form is nested in another form"
    assert depth == 0, f"{_name(path)}: unbalanced <form> tags"


@pytest.mark.parametrize("path", TEMPLATES, ids=_name)
def test_inline_handlers_only_interpolate_safe_values(path):
    offenders = []
    for handler in HANDLER.finditer(path.read_text()):
        for expression in EXPRESSION.findall(handler.group(1) or handler.group(2)):
            if "| tojson" not in expression and not SAFE_VALUE.search(expression):
                offenders.append(expression.strip())
    assert not offenders, f"{_name(path)}: unquoted values in an inline handler: {offenders}"
