# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the sandboxed template rendering service."""

import pytest
from mailler.services.rendering import (
    RenderError,
    convert_percent_syntax,
    html_template,
    render_parts,
    text_template,
)


class TestConvertPercentSyntax:
    def test_converts_variables(self):
        assert convert_percent_syntax("Hello %name%") == "Hello {{ name }}"

    def test_converts_several_variables(self):
        assert convert_percent_syntax("%first% %last%") == "{{ first }} {{ last }}"

    def test_leaves_plain_text(self):
        assert convert_percent_syntax("Hello world, 100% sure") == "Hello world, 100% sure"

    def test_leaves_escaped_percent(self):
        assert convert_percent_syntax("%%escaped%%") == "%%escaped%%"


class TestRenderParts:
    def test_renders_the_three_parts(self):
        rendered = render_parts(
            subject_template="Hi {{ name }}",
            html_compiled="<p>{{ name }}</p>",
            plain_text="Hello %name%",
            variables={"name": "Ann"},
        )
        assert rendered.subject == "Hi Ann"
        assert rendered.html == "<p>Ann</p>"
        assert rendered.plain_text == "Hello Ann"

    def test_without_plain_text(self):
        rendered = render_parts(
            subject_template="Hi",
            html_compiled="<p>x</p>",
            plain_text=None,
            variables={},
        )
        assert rendered.plain_text is None

    def test_html_is_escaped_and_text_is_not(self):
        rendered = render_parts(
            subject_template="{{ v }}",
            html_compiled="<p>{{ v }}</p>",
            plain_text="{{ v }}",
            variables={"v": "<a href='x'>&</a>"},
        )
        assert rendered.html == "<p>&lt;a href=&#39;x&#39;&gt;&amp;&lt;/a&gt;</p>"
        assert rendered.subject == "<a href='x'>&</a>"
        assert rendered.plain_text == "<a href='x'>&</a>"

    def test_missing_variable_renders_empty(self):
        rendered = render_parts(
            subject_template="Hi {{ name }}",
            html_compiled="<p>{{ name }}</p>",
            plain_text=None,
            variables={},
        )
        assert rendered.subject == "Hi "
        assert rendered.html == "<p></p>"

    def test_syntax_error(self):
        with pytest.raises(RenderError, match="syntax error"):
            render_parts(
                subject_template="{% if %}",
                html_compiled="<p></p>",
                plain_text=None,
                variables={},
            )

    def test_failing_expression(self):
        with pytest.raises(RenderError, match="Missing variable"):
            render_parts(
                subject_template="{{ user.name }}",
                html_compiled="<p></p>",
                plain_text=None,
                variables={},
            )

    @pytest.mark.parametrize(
        "expression",
        [
            "''.__class__.__mro__",
            "().__class__.__bases__",
            "cycler.__init__.__globals__",
        ],
    )
    def test_python_internals_are_out_of_reach(self, expression):
        for field in ("subject_template", "html_compiled", "plain_text"):
            kwargs = {
                "subject_template": "x",
                "html_compiled": "<p></p>",
                "plain_text": None,
                "variables": {},
            }
            kwargs[field] = "{{ " + expression + " }}"
            with pytest.raises(RenderError):
                render_parts(**kwargs)

    def test_private_attributes_render_nothing(self):
        rendered = render_parts(
            subject_template="[{{ lipsum.__globals__ }}]",
            html_compiled="<p></p>",
            plain_text=None,
            variables={},
        )
        assert rendered.subject == "[]"


class TestTemplateFactories:
    def test_html_template_escapes(self):
        assert html_template("{{ v }}").render(v="<b>") == "&lt;b&gt;"

    def test_text_template_does_not_escape(self):
        assert text_template("{{ v }}").render(v="<b>") == "<b>"

    def test_text_template_percent_syntax(self):
        assert text_template("Hi %v%", percent_syntax=True).render(v="x") == "Hi x"
        assert text_template("Hi %v%").render(v="x") == "Hi %v%"
