# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 login session for the web UI.

Implements Authorization Code + PKCE so the browser-based landing page can
authenticate the user without exposing a client secret in the frontend.

Flow:
1. ``GET /login`` → generate PKCE verifier + state, store in a short-lived
   cookie, redirect to ``auth``'s ``/oauth2/authorize``.
2. ``GET /callback`` → exchange the code for an access token via
   ``auth``'s ``/oauth2/token``, store the token in a signed session cookie.
3. Every subsequent page load: ``resolve_web_caller`` reads the session
   cookie, introspects if needed, and returns a ``Caller``.
4. ``GET /logout`` → clear the session cookie.
"""

import hashlib
import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass

from apt_server.config import settings


def _sign(payload: bytes) -> str:
    """Return base64(payload).base64(hmac) — simple signed cookie."""
    secret = (settings.session_secret or settings.oauth2_client_secret).encode()
    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    return urlsafe_b64encode(payload).decode() + "." + urlsafe_b64encode(sig).decode()


def _verify(token: str) -> bytes | None:
    """Verify and return payload, or None if tampered / expired."""
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    try:
        payload = urlsafe_b64decode(parts[0])
        sig = urlsafe_b64decode(parts[1])
    except Exception:
        return None
    secret = (settings.session_secret or settings.oauth2_client_secret).encode()
    expected = hmac.new(secret, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    return payload


@dataclass
class SessionData:
    token: str
    display_name: str = ""
    name: str = ""
    avatar_url: str = ""


def create_session_cookie(
    access_token: str,
    *,
    display_name: str = "",
    name: str = "",
    avatar_url: str = "",
) -> str:
    """Encode the access token + user info into a signed session cookie."""
    payload = json.dumps(
        {
            "token": access_token,
            "display_name": display_name,
            "name": name,
            "avatar_url": avatar_url,
            "iat": int(time.time()),
        }
    ).encode()
    return _sign(payload)


def read_session_cookie(cookie_value: str) -> SessionData | None:
    """Return session data from a session cookie, or None."""
    payload = _verify(cookie_value)
    if payload is None:
        return None
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    iat = data.get("iat", 0)
    if time.time() - iat > settings.session_max_age:
        return None
    token = data.get("token")
    if not token:
        return None
    return SessionData(
        token=token,
        display_name=data.get("display_name", ""),
        name=data.get("name", ""),
        avatar_url=data.get("avatar_url", ""),
    )


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def create_state_cookie(state: str, verifier: str) -> str:
    """Sign a (state, verifier) pair for the OAuth2 redirect round-trip."""
    payload = json.dumps({"state": state, "verifier": verifier}).encode()
    return _sign(payload)


def read_state_cookie(cookie_value: str) -> tuple[str, str] | None:
    """Return (state, verifier) from the state cookie, or None."""
    payload = _verify(cookie_value)
    if payload is None:
        return None
    try:
        data = json.loads(payload)
        return data["state"], data["verifier"]
    except (json.JSONDecodeError, KeyError):
        return None
