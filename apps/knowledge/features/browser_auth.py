# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The authentication service behind the sign-up and sign-in pages, for the browser scenarios.

``/auth/signup``, ``/auth/signin`` and the password pages call the authentication service
over HTTP (registration, e-mail verification, password grant, profile). The fake provider
of ``e2e-support`` only implements the OpenID endpoints, so this stand-in implements that
client interface on top of the provider's users: the tokens it hands out are signed by the
provider, so the application validates them exactly as it validates a token of the PKCE
login, and the provider accepts the same password afterwards.
"""

import secrets
import uuid

import jwt
from e2e_support.oidc import User
from e2e_support.oidc.tokens import issue_access_token, issue_refresh_token

from knowledge.services.auth_api import (
    AuthAPIError,
    MFAStatus,
    ProfileResult,
    RegisterResult,
    TokenResult,
)


class FakeAuthService:
    """Registration, verification, password grant and profile over the provider's users."""

    def __init__(self, provider, client):
        self.provider = provider
        self.client = client
        self.pending: dict[str, User] = {}
        self.codes: dict[str, str] = {}
        self.reset_tokens: dict[str, str] = {}
        self.nicknames: dict[str, str] = {}
        self.profiles: dict[str, dict] = {}

    # -- registration -----------------------------------------------------------------

    async def register(self, email, password, nickname=None, firstname=None, lastname=None):
        return self.preregister(email, password, nickname, firstname, lastname)

    def preregister(self, email, password, nickname=None, firstname=None, lastname=None):
        """Register a user (synchronous: the steps also use it to prepare accounts)."""
        if self.provider.user_by_email(email) or email in self.pending:
            raise AuthAPIError("Email already registered", "conflict")
        name = " ".join(part for part in (firstname, lastname) if part)
        user = User(email=email, name=name, password=password, id=str(uuid.uuid4()))
        self.pending[email] = user
        self.nicknames[user.id] = nickname or ""
        self.codes[email] = f"{secrets.randbelow(10**6):06d}"
        return RegisterResult(user_id=user.id, email=email, message="verification code sent")

    async def verify_email(self, email, code):
        if email not in self.pending or self.codes.get(email) != code:
            raise AuthAPIError("Invalid verification code")
        self.provider.add_user(self.pending.pop(email))
        return True

    async def resend_verification(self, email):
        if email in self.pending:
            self.codes[email] = f"{secrets.randbelow(10**6):06d}"
        return True

    # -- sign in ----------------------------------------------------------------------

    async def login(self, email, password, otp=None):
        if email in self.pending:
            raise AuthAPIError("Email not verified", "invalid_grant")
        user = self.provider.user_by_email(email)
        if user is None or user.password != password:
            raise AuthAPIError("Invalid credentials", "invalid_grant")
        scopes = ["openid", "profile", "email", "offline_access"]
        access = issue_access_token(
            self.provider, self.client, scopes, self.provider.issuer, user_id=user.id
        )
        refresh = issue_refresh_token(self.provider, self.client, scopes, user.id)
        return TokenResult(
            access_token=access,
            refresh_token=refresh,
            expires_in=self.provider.access_token_ttl,
            token_type="Bearer",
        )

    async def get_userinfo(self, access_token):
        user = self._user_of(access_token)
        return {"name": user.name, "email": user.email}

    # -- passwords --------------------------------------------------------------------

    async def forgot_password(self, email, reset_base_url=None):
        if self.provider.user_by_email(email) is None:
            raise AuthAPIError("unknown account")
        token = secrets.token_urlsafe(16)
        self.reset_tokens[token] = email
        return True

    async def reset_password(self, token, password):
        email = self.reset_tokens.pop(token, None)
        if email is None:
            raise AuthAPIError("Invalid or expired reset token")
        self.provider.user_by_email(email).password = password
        return True

    # -- account ----------------------------------------------------------------------

    def _user_of(self, access_token):
        sub = jwt.decode(access_token, options={"verify_signature": False}).get("sub")
        return self.provider.users[sub]

    async def get_profile(self, access_token):
        user = self._user_of(access_token)
        extra = self.profiles.get(user.id, {})
        return ProfileResult(
            sub=user.id,
            name=user.name,
            nickname=extra.get("nickname", self.nicknames.get(user.id) or None),
            given_name=extra.get("given_name"),
            family_name=extra.get("family_name"),
        )

    async def update_profile(self, access_token, **fields):
        user = self._user_of(access_token)
        self.profiles.setdefault(user.id, {}).update(
            {key: value for key, value in fields.items() if value is not None}
        )
        return await self.get_profile(access_token)

    async def get_mfa_status(self, access_token):
        return MFAStatus(totp_enabled=False)
