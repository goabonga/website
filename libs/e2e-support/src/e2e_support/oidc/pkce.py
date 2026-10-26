# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""PKCE (RFC 7636), with the same validation rules as the auth application."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets

#: Challenge methods the provider accepts.
METHODS = ("S256", "plain")

_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
_CHALLENGE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


def is_valid_method(method: str) -> bool:
    return method in METHODS


def is_valid_verifier(verifier: str) -> bool:
    """43 to 128 unreserved URI characters."""
    return bool(_VERIFIER.match(verifier))


def is_valid_challenge(challenge: str) -> bool:
    return bool(_CHALLENGE.match(challenge))


def challenge_for(verifier: str, method: str = "S256") -> str:
    """The challenge a client derives from its verifier (S256 or plain)."""
    if method == "S256":
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if method == "plain":
        return verifier
    raise ValueError(f"unsupported code challenge method: {method}")


def verify(verifier: str, challenge: str, method: str = "S256") -> bool:
    """Whether ``verifier`` matches the ``challenge`` received at authorization time."""
    try:
        return secrets.compare_digest(challenge_for(verifier, method), challenge)
    except (ValueError, UnicodeEncodeError):
        return False
