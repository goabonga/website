# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email MIME parser for inbound emails."""

import email
import email.utils
from dataclasses import dataclass, field
from email.header import decode_header
from email.message import Message

from mailler.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedAttachment:
    """Parsed email attachment."""

    filename: str
    content_type: str
    content: bytes
    content_id: str = ""


@dataclass
class ParsedEmail:
    """Parsed email structure."""

    message_id: str = ""
    in_reply_to: str | None = None
    from_email: str = ""
    from_name: str | None = None
    to: list[dict[str, str | None]] = field(default_factory=list)
    cc: list[dict[str, str | None]] = field(default_factory=list)
    reply_to_email: str | None = None
    reply_to_name: str | None = None
    subject: str = ""
    sent_at_date: str = ""
    html_body: str | None = None
    text_body: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    attachments: list[ParsedAttachment] = field(default_factory=list)


def _decode_header_value(value: str | None) -> str:
    """Decode an email header value handling charsets.

    Args:
        value: Raw header value.

    Returns:
        Decoded string.
    """
    if not value:
        return ""

    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _parse_address(addr_str: str | None) -> tuple[str, str | None]:
    """Parse an email address string into (email, name).

    Args:
        addr_str: Raw address string (e.g., "John Doe <john@example.com>").

    Returns:
        Tuple of (email, name).
    """
    if not addr_str:
        return ("", None)

    name, address = email.utils.parseaddr(addr_str)
    decoded_name = _decode_header_value(name) if name else None
    return (address, decoded_name)


def _parse_address_list(header_value: str | None) -> list[dict[str, str | None]]:
    """Parse a comma-separated address list.

    Args:
        header_value: Raw header value with multiple addresses.

    Returns:
        List of {Address, Name} dicts.
    """
    if not header_value:
        return []

    addresses = email.utils.getaddresses([header_value])
    result = []
    for name, addr in addresses:
        if addr:
            decoded_name = _decode_header_value(name) if name else None
            result.append({"Address": addr, "Name": decoded_name})
    return result


def _extract_body(msg: Message) -> tuple[str | None, str | None]:
    """Extract HTML and plain text bodies from a MIME message.

    Args:
        msg: Email message object.

    Returns:
        Tuple of (html_body, text_body).
    """
    html_body = None
    text_body = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            # Skip attachments
            if "attachment" in disposition:
                continue

            if content_type == "text/html" and html_body is None:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    html_body = payload.decode(charset, errors="replace")

            elif content_type == "text/plain" and text_body is None:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    text_body = payload.decode(charset, errors="replace")
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                html_body = decoded
            else:
                text_body = decoded

    return html_body, text_body


def _extract_attachments(msg: Message) -> list[ParsedAttachment]:
    """Extract attachments from a MIME message.

    Args:
        msg: Email message object.

    Returns:
        List of parsed attachments.
    """
    attachments: list[ParsedAttachment] = []

    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        disposition = str(part.get("Content-Disposition", ""))
        content_type = part.get_content_type()

        # Check if this part is an attachment
        is_attachment = "attachment" in disposition
        is_inline_with_name = "inline" in disposition and part.get_filename()

        # Skip non-attachment text parts
        if not is_attachment and not is_inline_with_name:
            if content_type in ("text/plain", "text/html"):
                continue
            if content_type.startswith("multipart/"):
                continue

        raw_payload = part.get_payload(decode=True)
        if not isinstance(raw_payload, bytes):
            continue

        filename = part.get_filename()
        if filename:
            filename = _decode_header_value(filename)
        else:
            filename = f"attachment.{content_type.split('/')[-1]}"

        content_id = part.get("Content-ID", "")
        if content_id:
            content_id = content_id.strip("<>")

        attachments.append(
            ParsedAttachment(
                filename=filename,
                content_type=content_type,
                content=raw_payload,
                content_id=content_id,
            )
        )

    return attachments


def _extract_headers(msg: Message) -> dict[str, str]:
    """Extract all headers from an email message.

    Args:
        msg: Email message object.

    Returns:
        Dict of header name to value.
    """
    headers = {}
    for key in msg:
        value = msg.get(key, "")
        headers[key] = _decode_header_value(value)
    return headers


def parse_email_bytes(raw_bytes: bytes) -> ParsedEmail:
    """Parse raw email bytes into a structured ParsedEmail.

    Args:
        raw_bytes: Raw RFC822 email bytes.

    Returns:
        ParsedEmail with all extracted data.
    """
    msg = email.message_from_bytes(raw_bytes)

    # Parse sender
    from_header = _decode_header_value(msg.get("From", ""))
    from_email, from_name = _parse_address(from_header)

    # Parse recipients
    to_list = _parse_address_list(_decode_header_value(msg.get("To", "")))
    cc_list = _parse_address_list(_decode_header_value(msg.get("Cc", "")))

    # Parse reply-to
    reply_to_header = _decode_header_value(msg.get("Reply-To", ""))
    reply_to_email, reply_to_name = _parse_address(reply_to_header)

    # Extract bodies
    html_body, text_body = _extract_body(msg)

    # Extract attachments
    attachments = _extract_attachments(msg)

    # Extract headers
    headers = _extract_headers(msg)

    parsed = ParsedEmail(
        message_id=_decode_header_value(msg.get("Message-ID", "")),
        in_reply_to=_decode_header_value(msg.get("In-Reply-To", "")) or None,
        from_email=from_email,
        from_name=from_name,
        to=to_list,
        cc=cc_list,
        reply_to_email=reply_to_email or None,
        reply_to_name=reply_to_name,
        subject=_decode_header_value(msg.get("Subject", "")),
        sent_at_date=_decode_header_value(msg.get("Date", "")),
        html_body=html_body,
        text_body=text_body,
        headers=headers,
        attachments=attachments,
    )

    logger.debug(
        "Parsed email",
        extra={
            "message_id": parsed.message_id,
            "from": parsed.from_email,
            "subject": parsed.subject,
            "attachments": len(parsed.attachments),
        },
    )

    return parsed


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown for ExtractedMarkdownMessage.

    Args:
        html: HTML content.

    Returns:
        Markdown representation.
    """
    try:
        import html2text

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = False
        converter.body_width = 0  # Don't wrap lines
        return converter.handle(html).strip()
    except ImportError:
        logger.warning("html2text not installed, returning empty markdown")
        return ""
