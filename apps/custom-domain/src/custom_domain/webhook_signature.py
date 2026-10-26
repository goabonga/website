# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Signature of the webhooks sent to the clients.

Standard library only: the service signs with :func:`signature_header` and a client
verifies with :func:`verify_signature` (the Python SDK exposes it in
``custom_domain.client.webhooks``). The signed text is ``"<timestamp>.<body>"`` with
HMAC-SHA256 and the client's webhook secret; the header is
``t=<unix timestamp>,v1=<hex digest>``. The timestamp lets a receiver reject old
deliveries (replays).
"""

import hashlib
import hmac
import time

SIGNATURE_HEADER = "X-Custom-Domain-Signature"
EVENT_HEADER = "X-Custom-Domain-Event"
DELIVERY_HEADER = "X-Custom-Domain-Delivery"

DEFAULT_TOLERANCE_SECONDS = 300


class SignatureError(ValueError):
    """The signature header is missing, malformed, wrong or too old."""


def sign(secret: str, body: bytes, timestamp: int) -> str:
    """Return the hex HMAC-SHA256 of ``"<timestamp>.<body>"``."""
    message = str(timestamp).encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signature_header(secret: str, body: bytes, timestamp: int | None = None) -> str:
    """Build the value of the signature header for ``body``."""
    stamp = int(time.time()) if timestamp is None else timestamp
    return f"t={stamp},v1={sign(secret, body, stamp)}"


def verify_signature(
    secret: str,
    body: bytes,
    header: str | None,
    tolerance_seconds: int | None = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> int:
    """Check a signature header against the raw request body.

    Args:
        secret: The client's webhook secret
        body: The raw body exactly as received (not re-serialized JSON)
        header: Value of the ``X-Custom-Domain-Signature`` header
        tolerance_seconds: Maximum age of the timestamp; ``None`` disables the check
        now: Current time (for tests)

    Returns:
        The timestamp of the delivery

    Raises:
        SignatureError: If the header is missing or malformed, no signature matches,
            or the timestamp is older (or newer) than the tolerance
    """
    if not header:
        raise SignatureError("Missing signature header")

    timestamp: int | None = None
    candidates: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as error:
                raise SignatureError("Malformed signature timestamp") from error
        elif key == "v1":
            candidates.append(value)
    if timestamp is None or not candidates:
        raise SignatureError("Malformed signature header")

    expected = sign(secret, body, timestamp)
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise SignatureError("Signature does not match")

    if tolerance_seconds is not None:
        current = time.time() if now is None else now
        if abs(current - timestamp) > tolerance_seconds:
            raise SignatureError("Timestamp outside the tolerance")

    return timestamp
