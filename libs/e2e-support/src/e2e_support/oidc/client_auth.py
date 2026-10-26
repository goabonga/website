# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Client authentication shared by the token, introspection and revocation endpoints."""

from __future__ import annotations

import base64
import binascii
import secrets
from typing import TYPE_CHECKING

from e2e_support.oidc.errors import OAuthError, invalid_client
from e2e_support.oidc.models import Client

if TYPE_CHECKING:
    from e2e_support.oidc.provider import FakeOIDCProvider


def parse_basic(authorization: str | None) -> tuple[str | None, str | None]:
    """The ``(client_id, client_secret)`` of an ``Authorization: Basic`` header."""
    if not authorization or not authorization.startswith("Basic "):
        return None, None
    try:
        decoded = base64.b64decode(authorization[6:]).decode("utf-8")
        client_id, client_secret = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None, None
    return client_id, client_secret


def authenticate(
    provider: FakeOIDCProvider,
    authorization: str | None,
    form: dict[str, str],
    *,
    missing_id_is_invalid_request: bool = False,
) -> Client:
    """Find the calling client and check its secret (Basic header wins over form fields).

    The token endpoint answers a missing ``client_id`` with ``400 invalid_request``; the
    introspection and revocation endpoints answer ``401 invalid_client``.
    """
    basic_id, basic_secret = parse_basic(authorization)
    client_id = basic_id or form.get("client_id")
    client_secret = basic_secret or form.get("client_secret")

    if not client_id:
        if missing_id_is_invalid_request:
            raise OAuthError("invalid_request", "client_id is required")
        raise invalid_client("Client authentication required")
    client = provider.clients.get(client_id)
    if client is None or not client.is_active:
        raise invalid_client("Invalid client")
    if client.is_confidential:
        if not client_secret:
            raise invalid_client("Client authentication required")
        if not secrets.compare_digest(client_secret, client.client_secret or ""):
            raise invalid_client("Invalid client credentials")
    return client
