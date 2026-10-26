# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-memory state of the fake provider: pending authorizations, codes and sessions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PendingAuthorization:
    """A validated authorization request waiting for the user to log in or consent."""

    client_id: str
    redirect_uri: str
    scopes: list[str]
    state: str | None
    code_challenge: str | None
    code_challenge_method: str | None
    nonce: str | None
    login_hint: str | None = None
    user_id: str | None = None


@dataclass
class AuthorizationCode:
    """An issued authorization code, redeemable once at the token endpoint."""

    code: str
    client_id: str
    redirect_uri: str
    user_id: str
    scopes: list[str]
    code_challenge: str | None
    code_challenge_method: str | None
    nonce: str | None
    auth_time: int
    expires_at: float
    used: bool = False


@dataclass
class Store:
    """Everything the provider remembers between requests."""

    pending: dict[str, PendingAuthorization] = field(default_factory=dict)
    codes: dict[str, AuthorizationCode] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)  # session id -> user id
