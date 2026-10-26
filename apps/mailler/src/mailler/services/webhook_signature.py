# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Webhook HMAC signature utilities.

Generates signatures for webhook verification since Brevo doesn't provide
native HMAC signatures for transactional webhooks.

The signature is included in the X-Mailin-custom header when sending emails
and verified by the webhooks service when receiving Brevo callbacks.
"""

import hashlib
import hmac
from typing import Any

from mailler.config import settings
from mailler.logging import get_logger

logger = get_logger(__name__)


def generate_webhook_signature(email_id: str, to_email: str) -> str:
    """Generate HMAC signature for webhook verification.

    The signature is based on email_id + to_email, ensuring that:
    1. Only webhooks for emails we sent are valid
    2. The signature is deterministic and can be recalculated

    Args:
        email_id: UUID of the email record
        to_email: Recipient email address (lowercased)

    Returns:
        HMAC-SHA256 signature as hex string
    """
    if not settings.webhook_hmac_secret:
        logger.warning("WEBHOOK_HMAC_SECRET not configured, signatures disabled")
        return ""

    # Normalize inputs
    message = f"{email_id}:{to_email.lower()}"

    signature = hmac.new(
        settings.webhook_hmac_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return signature


def verify_webhook_signature(
    email_id: str,
    to_email: str,
    signature: str,
) -> bool:
    """Verify HMAC signature from webhook.

    Args:
        email_id: UUID of the email record
        to_email: Recipient email address
        signature: Signature to verify

    Returns:
        True if signature is valid, False otherwise
    """
    if not settings.webhook_hmac_secret:
        logger.warning("WEBHOOK_HMAC_SECRET not configured, skipping verification")
        return True

    if not signature:
        logger.warning("No signature provided for verification")
        return False

    expected = generate_webhook_signature(email_id, to_email)
    if not expected:
        return True  # No secret configured

    is_valid = hmac.compare_digest(expected, signature.lower())

    if not is_valid:
        logger.warning(
            "Webhook signature mismatch | email_id=%s to_email=%s",
            email_id,
            to_email,
        )

    return is_valid


def build_mailin_custom(email_id: str, to_email: str, extra: dict[str, Any] | None = None) -> str:
    """Build X-Mailin-custom header value with signature.

    Format: "email_id:{uuid},signature:{hmac},key1:value1,..."

    Args:
        email_id: UUID of the email record
        to_email: Recipient email address
        extra: Additional key-value pairs to include

    Returns:
        X-Mailin-custom header value
    """
    parts = [f"email_id:{email_id}"]

    signature = generate_webhook_signature(email_id, to_email)
    if signature:
        parts.append(f"signature:{signature}")

    if extra:
        for key, value in extra.items():
            if value is not None:
                # Escape colons and commas in values
                safe_value = str(value).replace(",", "\\,").replace(":", "\\:")
                parts.append(f"{key}:{safe_value}")

    return ",".join(parts)


def parse_mailin_custom(header_value: str) -> dict[str, str]:
    """Parse X-Mailin-custom header value.

    Args:
        header_value: Raw header value

    Returns:
        Dictionary of key-value pairs
    """
    if not header_value:
        return {}

    result = {}
    current_key = ""
    current_value = ""
    in_value = False
    escaped = False

    for char in header_value:
        if escaped:
            current_value += char
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if char == ":" and not in_value:
            in_value = True
            continue

        if char == "," and in_value:
            result[current_key.strip()] = current_value.strip()
            current_key = ""
            current_value = ""
            in_value = False
            continue

        if in_value:
            current_value += char
        else:
            current_key += char

    # Don't forget the last pair
    if current_key:
        result[current_key.strip()] = current_value.strip()

    return result


# =============================================================================
# Unsubscribe signature utilities
# =============================================================================


def generate_unsubscribe_signature(email: str, client_id: str) -> str:
    """Generate HMAC signature for unsubscribe link verification.

    The signature covers the client the contact belongs to and the email
    address, so a link only ever unsubscribes the contact of one client and
    the recipient does not need to know any internal ID.

    Args:
        email: Recipient email address
        client_id: Client owning the contact

    Returns:
        HMAC-SHA256 signature as hex string (truncated to 32 chars for URL)
    """
    if not settings.webhook_hmac_secret:
        logger.warning("WEBHOOK_HMAC_SECRET not configured, unsubscribe signatures disabled")
        return ""

    # Use a different prefix to avoid collision with webhook signatures
    message = f"unsubscribe:{client_id}:{email.lower()}"

    signature = hmac.new(
        settings.webhook_hmac_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]  # Truncate for shorter URLs

    return signature


def verify_unsubscribe_signature(email: str, client_id: str, signature: str) -> bool:
    """Verify HMAC signature from unsubscribe request.

    Args:
        email: Recipient email address
        client_id: Client owning the contact
        signature: Signature to verify

    Returns:
        True if signature is valid, False otherwise
    """
    if not settings.webhook_hmac_secret:
        logger.warning("WEBHOOK_HMAC_SECRET not configured, rejecting unsubscribe")
        return False

    if not signature:
        logger.warning("No signature provided for unsubscribe verification")
        return False

    expected = generate_unsubscribe_signature(email, client_id)
    if not expected:
        return False

    is_valid = hmac.compare_digest(expected, signature.lower())

    if not is_valid:
        logger.warning(
            "Unsubscribe signature mismatch | email=%s",
            email,
        )

    return is_valid


def build_unsubscribe_url(email: str, client_id: str) -> str:
    """Build a signed unsubscribe URL for the given email.

    Args:
        email: Recipient email address
        client_id: Client owning the contact

    Returns:
        Full unsubscribe URL with signature, or empty string if not configured
    """
    from urllib.parse import quote

    if not settings.unsubscribe_base_url:
        return ""

    signature = generate_unsubscribe_signature(email, client_id)
    if not signature:
        return ""

    # URL encode the email to handle special characters
    encoded_email = quote(email.lower(), safe="")

    encoded_client = quote(client_id, safe="")

    return (
        f"{settings.unsubscribe_base_url}/unsubscribe"
        f"?email={encoded_email}&client={encoded_client}&sig={signature}"
    )
