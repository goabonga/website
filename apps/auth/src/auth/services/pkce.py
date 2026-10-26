# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""PKCE (Proof Key for Code Exchange) service.

Implements RFC 7636 for enhanced OAuth2 security.
"""

import base64
import hashlib
import re
import secrets


def generate_code_verifier(length: int = 64) -> str:
    """Generate a cryptographically random code verifier.

    Args:
        length: Length of the verifier (43-128 characters).

    Returns:
        URL-safe base64-encoded random string.
    """
    if length < 43 or length > 128:
        length = 64

    # Generate random bytes and encode to URL-safe base64
    random_bytes = secrets.token_bytes(length)
    verifier = base64.urlsafe_b64encode(random_bytes).decode().rstrip("=")

    # Truncate to desired length
    return verifier[:length]


def generate_code_challenge(verifier: str, method: str = "S256") -> str:
    """Generate a code challenge from a code verifier.

    Args:
        verifier: The code verifier.
        method: Challenge method ("S256" or "plain").

    Returns:
        The code challenge.

    Raises:
        ValueError: If method is not supported.
    """
    if method == "S256":
        # SHA-256 hash, then base64url encode
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
    elif method == "plain":
        return verifier
    else:
        raise ValueError(f"Unsupported code challenge method: {method}")


def verify_code_challenge(
    verifier: str,
    challenge: str,
    method: str = "S256",
) -> bool:
    """Verify a code verifier against a code challenge.

    Args:
        verifier: The code verifier from token request.
        challenge: The code challenge from authorization request.
        method: Challenge method ("S256" or "plain").

    Returns:
        True if verification succeeds.
    """
    try:
        expected_challenge = generate_code_challenge(verifier, method)
        return secrets.compare_digest(expected_challenge, challenge)
    except (ValueError, UnicodeDecodeError):
        return False


def is_valid_code_verifier(verifier: str) -> bool:
    """Check if a code verifier is valid per RFC 7636.

    Args:
        verifier: The code verifier to validate.

    Returns:
        True if valid.
    """
    if not verifier:
        return False

    # Must be 43-128 characters
    if len(verifier) < 43 or len(verifier) > 128:
        return False

    # Must only contain unreserved URI characters
    # A-Z, a-z, 0-9, -, ., _, ~
    pattern = r"^[A-Za-z0-9\-._~]+$"
    return bool(re.match(pattern, verifier))


def is_valid_code_challenge(challenge: str) -> bool:
    """Check if a code challenge is valid.

    Args:
        challenge: The code challenge to validate.

    Returns:
        True if valid.
    """
    if not challenge:
        return False

    # For S256, the challenge is base64url-encoded SHA-256 hash
    # Which is 43 characters without padding
    # For plain, same rules as verifier
    pattern = r"^[A-Za-z0-9\-_]+$"
    return bool(re.match(pattern, challenge))


def is_valid_code_challenge_method(method: str) -> bool:
    """Check if a code challenge method is valid.

    Args:
        method: The method to validate.

    Returns:
        True if valid.
    """
    return method in ("S256", "plain")
