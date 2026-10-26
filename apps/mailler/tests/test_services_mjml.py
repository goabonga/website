# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler/services/mjml.py."""

from unittest.mock import MagicMock, patch


class TestCompileMjml:
    """Tests for compile_mjml()."""

    async def test_successful_compilation(self):
        """Successful MJML compilation returns HTML and no errors."""
        mock_result = MagicMock()
        mock_result.content = "<html><body>Hello</body></html>"

        mock_mrml = MagicMock()
        mock_mrml.to_html.return_value = mock_result

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            from mailler.services.mjml import compile_mjml

            result = await compile_mjml("<mjml><mj-body></mj-body></mjml>")

        assert result["html"] == "<html><body>Hello</body></html>"
        assert result["errors"] is None

    async def test_converts_percent_vars_to_jinja(self):
        """Percent variables in compiled HTML are converted to Jinja2 syntax."""
        mock_result = MagicMock()
        mock_result.content = "<p>Hello %name%, your code is %code%</p>"

        mock_mrml = MagicMock()
        mock_mrml.to_html.return_value = mock_result

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            from mailler.services.mjml import compile_mjml

            result = await compile_mjml("<mjml><mj-body>%name% %code%</mj-body></mjml>")

        assert "{{name}}" in result["html"]
        assert "{{code}}" in result["html"]
        assert "%name%" not in result["html"]
        assert "%code%" not in result["html"]

    async def test_normalizes_line_endings(self):
        """Windows-style line endings (\\r\\n) are normalized to \\n before compilation."""
        mock_result = MagicMock()
        mock_result.content = "<html>ok</html>"

        mock_mrml = MagicMock()
        mock_mrml.to_html.return_value = mock_result

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            from mailler.services.mjml import compile_mjml

            source = "<mjml>\r\n<mj-body>\r\n</mj-body>\r\n</mjml>"
            await compile_mjml(source)

            # The source passed to mrml.to_html should have normalized line endings
            actual_call_arg = mock_mrml.to_html.call_args[0][0]
            assert "\r\n" not in actual_call_arg
            assert "\r" not in actual_call_arg

    async def test_compilation_error(self):
        """When mrml.to_html raises an exception, errors are returned."""
        mock_mrml = MagicMock()
        mock_mrml.to_html.side_effect = Exception("Invalid MJML structure")

        with patch.dict("sys.modules", {"mrml": mock_mrml}):
            from mailler.services.mjml import compile_mjml

            result = await compile_mjml("<bad>not valid</bad>")

        assert result["html"] == ""
        assert result["errors"] is not None
        assert len(result["errors"]) == 1
        assert "Invalid MJML structure" in result["errors"][0]


class TestExtractVariables:
    """Tests for extract_variables()."""

    def test_extracts_percent_vars(self):
        """Extracts variables using %var% syntax."""
        from mailler.services.mjml import extract_variables

        result = extract_variables("Hello %name%, your order %order_id% is ready")
        assert "name" in result
        assert "order_id" in result

    def test_extracts_jinja_vars(self):
        """Extracts variables using {{var}} syntax."""
        from mailler.services.mjml import extract_variables

        result = extract_variables("Hello {{name}}, your order {{ order_id }} is ready")
        assert "name" in result
        assert "order_id" in result

    def test_extracts_from_subject(self):
        """Extracts variables from the subject line as well."""
        from mailler.services.mjml import extract_variables

        result = extract_variables("Body text", subject="Hello %username%")
        assert "username" in result

    def test_unique_preserving_order(self):
        """Duplicate variables are removed but order is preserved."""
        from mailler.services.mjml import extract_variables

        result = extract_variables("%alpha% %beta% %alpha% %gamma% %beta%")
        assert result == ["alpha", "beta", "gamma"]

    def test_empty_source(self):
        """Empty source returns an empty list."""
        from mailler.services.mjml import extract_variables

        result = extract_variables("")
        assert result == []


class TestHtmlToPlainText:
    """Tests for html_to_plain_text()."""

    def test_strips_tags(self):
        """HTML tags are removed, leaving only text."""
        from mailler.services.mjml import html_to_plain_text

        result = html_to_plain_text("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<p>" not in result
        assert "<b>" not in result

    def test_removes_scripts_and_styles(self):
        """Script and style elements are completely removed."""
        from mailler.services.mjml import html_to_plain_text

        html = (
            "<html><head><style>body { color: red; }</style></head>"
            "<body><script>alert('x')</script><p>Visible text</p></body></html>"
        )
        result = html_to_plain_text(html)
        assert "Visible text" in result
        assert "alert" not in result
        assert "color: red" not in result

    def test_returns_empty_on_error(self):
        """Returns empty string when BeautifulSoup raises an exception."""
        with patch("mailler.services.mjml.BeautifulSoup", side_effect=Exception("Parse error")):
            from mailler.services.mjml import html_to_plain_text

            result = html_to_plain_text("<p>Some HTML</p>")

        assert result == ""


class TestValidateMjml:
    """Tests for validate_mjml()."""

    def test_valid_mjml(self):
        """Valid MJML source passes validation."""
        from mailler.services.mjml import validate_mjml

        is_valid, errors = validate_mjml("<mjml><mj-body></mj-body></mjml>")
        assert is_valid is True
        assert errors == []

    def test_empty_source(self):
        """Empty source fails validation."""
        from mailler.services.mjml import validate_mjml

        is_valid, errors = validate_mjml("")
        assert is_valid is False
        assert any("empty" in e.lower() for e in errors)

    def test_missing_mjml_tag(self):
        """Source without <mjml> tag fails validation."""
        from mailler.services.mjml import validate_mjml

        is_valid, errors = validate_mjml("<mj-body>Hello</mj-body></mjml>")
        assert is_valid is False
        assert any("<mjml>" in e for e in errors)

    def test_missing_closing_tag(self):
        """Source without </mjml> closing tag fails validation."""
        from mailler.services.mjml import validate_mjml

        is_valid, errors = validate_mjml("<mjml><mj-body>Hello</mj-body>")
        assert is_valid is False
        assert any("</mjml>" in e for e in errors)
