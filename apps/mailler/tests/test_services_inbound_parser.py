# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.services.inbound.parser module."""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

from mailler.services.inbound.parser import (
    ParsedEmail,
    _decode_header_value,
    _extract_attachments,
    _extract_body,
    _extract_headers,
    _parse_address,
    _parse_address_list,
    html_to_markdown,
    parse_email_bytes,
)


class TestDecodeHeaderValue:
    """Tests for _decode_header_value()."""

    def test_none_input(self):
        assert _decode_header_value(None) == ""

    def test_empty_string(self):
        assert _decode_header_value("") == ""

    def test_plain_ascii(self):
        assert _decode_header_value("Hello World") == "Hello World"

    def test_encoded_utf8(self):
        result = _decode_header_value("=?utf-8?B?SMOpbMOobmU=?=")
        assert "H" in result


class TestParseAddress:
    """Tests for _parse_address()."""

    def test_none_input(self):
        email, name = _parse_address(None)
        assert email == ""
        assert name is None

    def test_email_only(self):
        email, name = _parse_address("test@example.com")
        assert email == "test@example.com"
        assert name is None

    def test_name_and_email(self):
        email, name = _parse_address("John Doe <john@example.com>")
        assert email == "john@example.com"
        assert name == "John Doe"


class TestParseAddressList:
    """Tests for _parse_address_list()."""

    def test_none_input(self):
        assert _parse_address_list(None) == []

    def test_single_address(self):
        result = _parse_address_list("test@example.com")
        assert len(result) == 1
        assert result[0]["Address"] == "test@example.com"

    def test_multiple_addresses(self):
        result = _parse_address_list("a@t.com, b@t.com")
        assert len(result) == 2

    def test_address_with_empty_addr_skipped(self):
        """Cover branch line 98->97: address entry with empty addr is skipped."""
        # An undisclosed-recipients header typically gives an empty addr
        result = _parse_address_list("undisclosed-recipients:;")
        # The undisclosed-recipients group produces no valid addresses
        assert result == []


class TestExtractBody:
    """Tests for _extract_body()."""

    def test_multipart(self):
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("Hello text", "plain", "utf-8"))
        msg.attach(MIMEText("<p>Hello HTML</p>", "html", "utf-8"))

        html, text = _extract_body(msg)
        assert "Hello HTML" in html
        assert "Hello text" in text

    def test_single_part_html(self):
        msg = MIMEText("<p>Only HTML</p>", "html", "utf-8")
        html, text = _extract_body(msg)
        assert "Only HTML" in html
        assert text is None

    def test_single_part_text(self):
        msg = MIMEText("Only text", "plain", "utf-8")
        html, text = _extract_body(msg)
        assert html is None
        assert "Only text" in text

    def test_multipart_non_bytes_html_payload(self):
        """Cover branch line 127->117: multipart HTML part with non-bytes payload."""
        # Build a fully mocked message so walk() yields our controlled parts
        html_part = MagicMock()
        html_part.get_content_type.return_value = "text/html"
        html_part.get.return_value = ""
        html_part.get_payload.return_value = "not bytes"  # non-bytes

        msg = MagicMock()
        msg.is_multipart.return_value = True
        msg.walk.return_value = [html_part]

        html, text = _extract_body(msg)
        # HTML part was skipped because payload is not bytes
        assert html is None

    def test_multipart_non_bytes_text_payload(self):
        """Cover branch line 133->117: multipart text part with non-bytes payload."""
        text_part = MagicMock()
        text_part.get_content_type.return_value = "text/plain"
        text_part.get.return_value = ""
        text_part.get_payload.return_value = "not bytes"  # non-bytes

        msg = MagicMock()
        msg.is_multipart.return_value = True
        msg.walk.return_value = [text_part]

        html, text = _extract_body(msg)
        # text part was skipped because payload is not bytes
        assert text is None

    def test_single_part_non_bytes_payload(self):
        """Cover branch line 139->147: single-part message with non-bytes payload."""
        msg = MagicMock()
        msg.is_multipart.return_value = False
        msg.get_content_type.return_value = "text/plain"
        msg.get_payload.return_value = "not bytes"  # non-bytes

        html, text = _extract_body(msg)
        assert html is None
        assert text is None


class TestExtractAttachments:
    """Tests for _extract_attachments()."""

    def test_no_attachments(self):
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("body", "plain"))
        result = _extract_attachments(msg)
        assert result == []

    def test_single_part_no_attachments(self):
        msg = MIMEText("body", "plain")
        result = _extract_attachments(msg)
        assert result == []

    def test_with_attachment(self):
        msg = MIMEMultipart("mixed")
        msg.attach(MIMEText("body", "plain"))

        att = MIMEBase("application", "pdf")
        att.set_payload(b"fake pdf content")
        encoders.encode_base64(att)
        att.add_header("Content-Disposition", "attachment", filename="doc.pdf")
        msg.attach(att)

        result = _extract_attachments(msg)
        assert len(result) == 1
        assert result[0].filename == "doc.pdf"
        assert result[0].content_type == "application/pdf"

    def test_inline_with_content_id(self):
        msg = MIMEMultipart("mixed")
        msg.attach(MIMEText("body", "plain"))

        att = MIMEBase("image", "png")
        att.set_payload(b"fake png")
        encoders.encode_base64(att)
        att.add_header("Content-Disposition", "inline", filename="img.png")
        att.add_header("Content-ID", "<img001>")
        msg.attach(att)

        result = _extract_attachments(msg)
        assert len(result) == 1
        assert result[0].content_id == "img001"

    def test_skips_multipart_content_type(self):
        """Cover branch line 176->179: multipart/ content type parts are skipped."""
        # Use a fully mocked message to control walk() output
        multipart_part = MagicMock()
        multipart_part.get.side_effect = lambda header, default="": default
        multipart_part.get_content_type.return_value = "multipart/alternative"
        multipart_part.get_filename.return_value = None

        attachment_part = MagicMock()
        attachment_part.get.side_effect = lambda header, default="": (
            "attachment; filename=doc.pdf" if header == "Content-Disposition" else default
        )
        attachment_part.get_content_type.return_value = "application/pdf"
        attachment_part.get_payload.return_value = b"data"
        attachment_part.get_filename.return_value = "doc.pdf"

        msg = MagicMock()
        msg.is_multipart.return_value = True
        msg.walk.return_value = [multipart_part, attachment_part]

        result = _extract_attachments(msg)
        # Only the PDF attachment should be found, not the inner multipart
        assert len(result) == 1
        assert result[0].filename == "doc.pdf"

    def test_skips_non_bytes_attachment_payload(self):
        """Cover line 181: attachment part with non-bytes payload is skipped."""
        att_part = MagicMock()
        att_part.get.side_effect = lambda header, default="": (
            "attachment; filename=test.bin" if header == "Content-Disposition" else default
        )
        att_part.get_content_type.return_value = "application/octet-stream"
        att_part.get_payload.return_value = None  # non-bytes
        att_part.get_filename.return_value = "test.bin"

        msg = MagicMock()
        msg.is_multipart.return_value = True
        msg.walk.return_value = [att_part]

        result = _extract_attachments(msg)
        # The non-bytes attachment should be skipped
        assert len(result) == 0

    def test_non_text_non_multipart_non_attachment_part(self):
        """Cover branch line 176->179 (False): part with non-text, non-multipart
        content type that is not an attachment falls through to payload extraction."""
        # A part like image/png with no Content-Disposition (no attachment/inline)
        # and no filename. It should fall through lines 173-177 to line 179.
        image_part = MagicMock()
        image_part.get.side_effect = lambda header, default="": default
        image_part.get_content_type.return_value = "image/png"
        image_part.get_filename.return_value = None
        image_part.get_payload.return_value = b"fake-image-data"

        msg = MagicMock()
        msg.is_multipart.return_value = True
        msg.walk.return_value = [image_part]

        result = _extract_attachments(msg)
        # The image part should be treated as an attachment with generated filename
        assert len(result) == 1
        assert result[0].filename == "attachment.png"
        assert result[0].content_type == "image/png"

    def test_attachment_without_filename(self):
        """Cover line 187: attachment without filename gets generated name."""
        msg = MIMEMultipart("mixed")
        msg.attach(MIMEText("body", "plain"))

        att = MIMEBase("image", "jpeg")
        att.set_payload(b"fake jpeg data")
        encoders.encode_base64(att)
        # Add disposition without filename
        att.add_header("Content-Disposition", "attachment")
        msg.attach(att)

        result = _extract_attachments(msg)
        assert len(result) == 1
        # Generated filename based on content type
        assert result[0].filename == "attachment.jpeg"


class TestExtractHeaders:
    """Tests for _extract_headers()."""

    def test_extracts_all_headers(self):
        msg = MIMEText("body", "plain")
        msg["X-Custom"] = "custom-value"
        headers = _extract_headers(msg)
        assert "X-Custom" in headers
        assert headers["X-Custom"] == "custom-value"


class TestParseEmailBytes:
    """Tests for parse_email_bytes()."""

    def test_simple_email(self):
        msg = MIMEText("Hello world", "plain", "utf-8")
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "Test Subject"
        msg["Message-ID"] = "<msg001@example.com>"
        msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"

        parsed = parse_email_bytes(msg.as_bytes())

        assert isinstance(parsed, ParsedEmail)
        assert parsed.from_email == "sender@example.com"
        assert parsed.subject == "Test Subject"
        assert parsed.message_id == "<msg001@example.com>"
        assert parsed.text_body == "Hello world"
        assert len(parsed.to) == 1

    def test_multipart_with_attachment(self):
        msg = MIMEMultipart("mixed")
        msg["From"] = "John <john@example.com>"
        msg["To"] = "jane@example.com"
        msg["Subject"] = "With attachment"
        msg["Reply-To"] = "reply@example.com"

        msg.attach(MIMEText("<p>HTML body</p>", "html", "utf-8"))

        att = MIMEBase("application", "octet-stream")
        att.set_payload(b"file content")
        encoders.encode_base64(att)
        att.add_header("Content-Disposition", "attachment", filename="test.txt")
        msg.attach(att)

        parsed = parse_email_bytes(msg.as_bytes())

        assert parsed.from_name == "John"
        assert parsed.reply_to_email == "reply@example.com"
        assert parsed.html_body is not None
        assert len(parsed.attachments) == 1
        assert parsed.attachments[0].filename == "test.txt"

    def test_in_reply_to(self):
        msg = MIMEText("reply", "plain")
        msg["From"] = "a@t.com"
        msg["To"] = "b@t.com"
        msg["Subject"] = "Re: Test"
        msg["In-Reply-To"] = "<orig@t.com>"

        parsed = parse_email_bytes(msg.as_bytes())
        assert parsed.in_reply_to == "<orig@t.com>"

    def test_cc_recipients(self):
        msg = MIMEText("body", "plain")
        msg["From"] = "a@t.com"
        msg["To"] = "b@t.com"
        msg["Cc"] = "c@t.com, d@t.com"
        msg["Subject"] = "Test"

        parsed = parse_email_bytes(msg.as_bytes())
        assert len(parsed.cc) == 2


class TestHtmlToMarkdown:
    """Tests for html_to_markdown()."""

    def test_basic_html(self):
        result = html_to_markdown("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result

    def test_with_link(self):
        result = html_to_markdown('<a href="https://example.com">Click</a>')
        assert "Click" in result

    def test_empty_html(self):
        result = html_to_markdown("")
        assert result == "" or isinstance(result, str)

    def test_html2text_import_error(self):
        """Cover lines 300-302: html2text not installed returns empty string."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "html2text":
                raise ImportError("No module named 'html2text'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = html_to_markdown("<p>Hello</p>")

        assert result == ""
