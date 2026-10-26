# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures for 100% mocked unit tests."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helper: create a mock that behaves like SQLAlchemy AsyncSession
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a fully mocked async database session.

    All DB operations (execute, flush, commit, refresh, delete, add) are
    AsyncMocks so they can be awaited without touching any real database.
    """
    session = AsyncMock()
    session.add = MagicMock()
    return session


def make_execute_result(scalar_value=None, scalars_list=None, all_rows=None):
    """Build a mock result object returned by ``db.execute()``.

    Args:
        scalar_value: Value returned by ``result.scalar_one_or_none()``.
        scalars_list: Value returned by ``result.scalars().all()``.
        all_rows: Value returned by ``result.all()`` (for grouped queries).

    Returns:
        A MagicMock that mimics an SQLAlchemy Result.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value

    if scalars_list is not None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_list
        result.scalars.return_value = scalars_mock

    if all_rows is not None:
        result.all.return_value = all_rows

    # Also support result.scalar() for count queries
    if scalar_value is not None:
        result.scalar.return_value = scalar_value

    return result


# ---------------------------------------------------------------------------
# Mock model factories
# ---------------------------------------------------------------------------


def make_user(
    user_id=None,
    is_active=True,
    passwords=None,
    registration_source=None,
):
    """Create a mock User model."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.is_active = is_active
    user.passwords = passwords or []
    user.registration_source = registration_source
    return user


def make_user_email(
    email="test@example.com",
    user_id=None,
    user=None,
    is_primary=True,
    is_verified=True,
):
    """Create a mock UserEmail model."""
    ue = MagicMock()
    ue.id = uuid.uuid4()
    ue.email = email
    ue.user_id = user_id or uuid.uuid4()
    ue.user = user or make_user(user_id=ue.user_id)
    ue.is_primary = is_primary
    ue.is_verified = is_verified
    ue.created_at = datetime.now(UTC)
    return ue


def make_user_password(password_hash="hashed_pw", is_current=True):
    """Create a mock UserPassword model."""
    pwd = MagicMock()
    pwd.password_hash = password_hash
    pwd.is_current = is_current
    return pwd


def make_oauth2_client(
    client_id=None,
    client_secret_hash=None,
    name="Test App",
    redirect_uris=None,
    allowed_scopes=None,
    allowed_grant_types=None,
    is_confidential=True,
    require_pkce=True,
    access_token_expiry_seconds=None,
    refresh_token_expiry_seconds=None,
    allowed_origins=None,
    homepage_url=None,
    description=None,
):
    """Create a mock OAuth2Client model."""
    client = MagicMock()
    client.id = uuid.uuid4()
    client.client_id = client_id or "test_client_id"
    client.client_secret_hash = client_secret_hash
    client.name = name
    client.redirect_uris = (
        redirect_uris if redirect_uris is not None else ["https://app.example.com/callback"]
    )
    client.allowed_scopes = (
        allowed_scopes if allowed_scopes is not None else ["openid", "profile", "email"]
    )
    client.allowed_grant_types = (
        allowed_grant_types
        if allowed_grant_types is not None
        else ["authorization_code", "refresh_token"]
    )
    client.is_confidential = is_confidential
    client.require_pkce = require_pkce
    client.require_consent = True
    client.access_token_expiry_seconds = access_token_expiry_seconds
    client.refresh_token_expiry_seconds = refresh_token_expiry_seconds
    client.allowed_origins = allowed_origins
    client.homepage_url = homepage_url
    client.description = description
    return client


def make_jwk(
    kid=None,
    is_active=True,
    revoked_at=None,
    public_key_pem="fake_public_pem",
    private_key_encrypted=b"fake_encrypted",
):
    """Create a mock JWK model."""
    jwk = MagicMock()
    jwk.id = uuid.uuid4()
    jwk.kid = kid or str(uuid.uuid4())
    jwk.kty = "RSA"
    jwk.alg = "RS256"
    jwk.use = "sig"
    jwk.is_active = is_active
    jwk.revoked_at = revoked_at
    jwk.public_key_pem = public_key_pem
    jwk.private_key_encrypted = private_key_encrypted
    jwk.created_at = datetime.now(UTC)
    return jwk


def make_session(
    user_id=None,
    session_token_hash="hashed_session",
    csrf_token_hash="hashed_csrf",
    expires_at=None,
    revoked_at=None,
):
    """Create a mock Session model."""
    s = MagicMock()
    s.id = uuid.uuid4()
    s.user_id = user_id or uuid.uuid4()
    s.session_token_hash = session_token_hash
    s.csrf_token_hash = csrf_token_hash
    s.expires_at = expires_at or (datetime.now(UTC) + timedelta(days=7))
    s.revoked_at = revoked_at
    s.created_at = datetime.now(UTC)
    s.ip_address = "127.0.0.1"
    s.user_agent = "TestAgent/1.0"
    return s


def make_access_token(
    jti=None,
    client_id=None,
    user_id=None,
    scopes=None,
    revoked_at=None,
    expires_at=None,
):
    """Create a mock AccessToken model."""
    at = MagicMock()
    at.id = uuid.uuid4()
    at.jti = jti or str(uuid.uuid4())
    at.client_id = client_id or uuid.uuid4()
    at.user_id = user_id or uuid.uuid4()
    at.scopes = scopes or ["openid"]
    at.revoked_at = revoked_at
    at.expires_at = expires_at or (datetime.now(UTC) + timedelta(hours=1))
    at.created_at = datetime.now(UTC)
    return at


def make_refresh_token(
    token_hash="hashed_refresh",
    client_id=None,
    user_id=None,
    scopes=None,
    revoked_at=None,
    used_at=None,
    expires_at=None,
    access_token_id=None,
):
    """Create a mock RefreshToken model."""
    rt = MagicMock()
    rt.id = uuid.uuid4()
    rt.token_hash = token_hash
    rt.client_id = client_id or uuid.uuid4()
    rt.user_id = user_id or uuid.uuid4()
    rt.scopes = scopes or ["openid"]
    rt.revoked_at = revoked_at
    rt.used_at = used_at
    rt.expires_at = expires_at or (datetime.now(UTC) + timedelta(days=30))
    rt.access_token_id = access_token_id or uuid.uuid4()
    return rt


def make_password_reset_token(
    user_id=None,
    email="test@example.com",
    token_hash="hashed_reset",
    used_at=None,
    expires_at=None,
):
    """Create a mock PasswordResetToken model."""
    prt = MagicMock()
    prt.id = uuid.uuid4()
    prt.user_id = user_id or uuid.uuid4()
    prt.email = email
    prt.token_hash = token_hash
    prt.used_at = used_at
    prt.expires_at = expires_at or (datetime.now(UTC) + timedelta(hours=1))
    prt.created_at = datetime.now(UTC)
    return prt


def make_user_mfa(
    user_id=None,
    totp_enabled=False,
    totp_secret_encrypted=None,
    backup_codes=None,
):
    """Create a mock UserMFA model."""
    mfa = MagicMock()
    mfa.id = uuid.uuid4()
    mfa.user_id = user_id or uuid.uuid4()
    mfa.totp_enabled = totp_enabled
    mfa.totp_secret_encrypted = totp_secret_encrypted
    mfa.totp_enabled_at = None
    mfa.backup_codes = backup_codes or []
    return mfa


def make_backup_code(code_hash="hashed_backup", used_at=None):
    """Create a mock MFABackupCode model."""
    bc = MagicMock()
    bc.id = uuid.uuid4()
    bc.code_hash = code_hash
    bc.used_at = used_at
    return bc


def make_device_code(
    device_code_hash="hashed_device",
    user_code="ABCD-EFGH",
    client_id=None,
    scopes=None,
    status="pending",
    user_id=None,
    expires_at=None,
    last_poll_at=None,
    interval=5,
):
    """Create a mock DeviceCode model."""
    dc = MagicMock()
    dc.id = uuid.uuid4()
    dc.device_code_hash = device_code_hash
    dc.user_code = user_code
    dc.client_id = client_id or uuid.uuid4()
    dc.scopes = scopes or ["openid"]
    dc.status = status
    dc.user_id = user_id
    dc.expires_at = expires_at or (datetime.now(UTC) + timedelta(minutes=15))
    dc.last_poll_at = last_poll_at
    dc.interval = interval
    dc.verification_uri = "https://auth.example.com/device"
    return dc


def make_authorization_code(
    code_hash="hashed_auth_code",
    client_id=None,
    user_id=None,
    redirect_uri="https://app.example.com/callback",
    scopes=None,
    code_challenge=None,
    code_challenge_method=None,
    nonce=None,
    state=None,
    used_at=None,
    expires_at=None,
):
    """Create a mock AuthorizationCode model."""
    ac = MagicMock()
    ac.id = uuid.uuid4()
    ac.code_hash = code_hash
    ac.client_id = client_id or uuid.uuid4()
    ac.user_id = user_id or str(uuid.uuid4())
    ac.redirect_uri = redirect_uri
    ac.scopes = scopes or ["openid"]
    ac.code_challenge = code_challenge
    ac.code_challenge_method = code_challenge_method
    ac.nonce = nonce
    ac.state = state
    ac.used_at = used_at
    ac.expires_at = expires_at or (datetime.now(UTC) + timedelta(minutes=10))
    return ac


def make_personal_access_token(
    user_id=None,
    name="My Token",
    token_hash="hashed_pat",
    token_suffix="abcd",
    scopes=None,
    expires_at=None,
    revoked_at=None,
    use_count=0,
    user=None,
):
    """Create a mock PersonalAccessToken model."""
    pat = MagicMock()
    pat.id = uuid.uuid4()
    pat.user_id = user_id or uuid.uuid4()
    pat.name = name
    pat.description = None
    pat.token_hash = token_hash
    pat.token_suffix = token_suffix
    pat.scopes = scopes or ["openid"]
    pat.expires_at = expires_at
    pat.revoked_at = revoked_at
    pat.revoked_by = None
    pat.revocation_reason = None
    pat.last_used_at = None
    pat.last_used_ip = None
    pat.use_count = use_count
    pat.tenant_id = None
    pat.target_client_id = None
    pat.created_at = datetime.now(UTC)
    pat.user = user or make_user(user_id=pat.user_id)
    return pat
