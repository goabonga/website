# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for email rendering service."""

from unittest.mock import MagicMock, patch

from internal.services.email_renderer import EmailRenderer, get_email_renderer


class TestExtractVariables:
    def setup_method(self):
        self.renderer = EmailRenderer()

    def test_percent_syntax(self):
        mjml = "<mj-text>Hello %first_name%, your email is %email%</mj-text>"
        result = self.renderer.extract_variables(mjml)
        assert result == ["first_name", "email"]

    def test_jinja_syntax(self):
        html = "<p>Hello {{ first_name }}, your email is {{ email }}</p>"
        result = self.renderer.extract_variables(html)
        assert result == ["first_name", "email"]

    def test_both_syntaxes(self):
        source = "<p>%name% and {{ email }}</p>"
        result = self.renderer.extract_variables(source)
        assert result == ["name", "email"]

    def test_dedup_preserves_order(self):
        source = "%name% %email% %name% %email%"
        result = self.renderer.extract_variables(source)
        assert result == ["name", "email"]

    def test_subject_included(self):
        result = self.renderer.extract_variables("", subject="Hello %name%!")
        assert result == ["name"]

    def test_empty_source(self):
        result = self.renderer.extract_variables("")
        assert result == []


class TestHtmlToPlainText:
    def setup_method(self):
        self.renderer = EmailRenderer()

    def test_basic_html(self):
        html = "<p>Hello <b>World</b></p>"
        result = self.renderer.html_to_plain_text(html)
        assert "Hello" in result
        assert "World" in result
        assert "<p>" not in result

    def test_removes_scripts(self):
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        result = self.renderer.html_to_plain_text(html)
        assert "alert" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_style(self):
        html = "<style>.cls{color:red}</style><p>Content</p>"
        result = self.renderer.html_to_plain_text(html)
        assert "color:red" not in result
        assert "Content" in result

    def test_empty_html(self):
        assert self.renderer.html_to_plain_text("") == ""


class TestRenderTemplate:
    def setup_method(self):
        self.renderer = EmailRenderer()

    def test_render_with_variables(self):
        html = "<p>Hello {{ name }}, email: {{ email }}</p>"
        rendered_html, rendered_subject = self.renderer.render_template(
            html, {"name": "John", "email": "john@test.com"}, subject="Hi {{ name }}"
        )
        assert "John" in rendered_html
        assert "john@test.com" in rendered_html
        assert rendered_subject == "Hi John"

    def test_missing_var_returns_empty(self):
        html = "<p>Hello {{ name }}</p>"
        rendered_html, _ = self.renderer.render_template(html, {})
        assert "{{ name }}" not in rendered_html

    def test_render_error_returns_original(self):
        html = "{% invalid jinja %}"
        rendered_html, rendered_subject = self.renderer.render_template(html, {}, subject="Subject")
        assert rendered_html == html
        assert rendered_subject == "Subject"


class TestValidateMjml:
    def setup_method(self):
        self.renderer = EmailRenderer()

    def test_empty_source(self):
        valid, errors = self.renderer.validate_mjml("")
        assert valid is False
        assert "empty" in errors[0].lower()

    def test_missing_root_element(self):
        valid, errors = self.renderer.validate_mjml("<div>not mjml</div>")
        assert valid is False
        assert "Missing <mjml>" in errors[0]

    def test_missing_closing_tag(self):
        valid, errors = self.renderer.validate_mjml("<mjml><mj-body>")
        assert valid is False
        assert "Missing </mjml>" in errors[0]

    def test_valid_mjml(self):
        mock_mrml = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "<html><body>compiled</body></html>"
        mock_mrml.to_html.return_value = mock_result

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            valid, errors = self.renderer.validate_mjml(
                "<mjml><mj-body><mj-section></mj-section></mj-body></mjml>"
            )
        assert valid is True
        assert errors == []


class TestCompileMjml:
    def setup_method(self):
        self.renderer = EmailRenderer()

    def test_compile_success(self):
        mock_mrml = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "<html>Hello %name%</html>"
        mock_mrml.to_html.return_value = mock_result

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            html, errors = self.renderer.compile_mjml("<mjml><mj-body></mj-body></mjml>")
        assert "{{name}}" in html
        assert errors == []

    def test_compile_converts_percent_to_jinja(self):
        mock_mrml = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "<p>%first_name% %last_name%</p>"
        mock_mrml.to_html.return_value = mock_result

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            html, errors = self.renderer.compile_mjml("<mjml></mjml>")
        assert "{{first_name}}" in html
        assert "{{last_name}}" in html

    def test_compile_error(self):
        mock_mrml = MagicMock()
        mock_mrml.to_html.side_effect = Exception("Parse error")

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            html, errors = self.renderer.compile_mjml("<invalid>")
        assert html == ""
        assert len(errors) == 1
        assert "Parse error" in errors[0]

    def test_compile_normalizes_line_endings(self):
        mock_mrml = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "<html></html>"
        mock_mrml.to_html.return_value = mock_result

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            self.renderer.compile_mjml("<mjml>\r\n<mj-body>\r\n</mj-body>\r\n</mjml>")
        call_arg = mock_mrml.to_html.call_args[0][0]
        assert "\r\n" not in call_arg


class TestGetDefaultMjml:
    def test_returns_default_template(self):
        renderer = EmailRenderer()
        mjml = renderer.get_default_mjml()
        assert "<mjml>" in mjml
        assert "</mjml>" in mjml
        assert "%subject%" in mjml


class TestHtmlToPlainTextException:
    def test_returns_empty_on_error(self):
        renderer = EmailRenderer()
        with patch(
            "internal.services.email_renderer.BeautifulSoup", side_effect=Exception("parse error")
        ):
            result = renderer.html_to_plain_text("<p>test</p>")
            assert result == ""


class TestSingleton:
    @patch("internal.services.email_renderer._renderer", None)
    def test_creates_singleton(self):
        r1 = get_email_renderer()
        r2 = get_email_renderer()
        assert r1 is r2
        assert isinstance(r1, EmailRenderer)
