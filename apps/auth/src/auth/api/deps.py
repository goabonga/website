# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI dependencies for dependency injection."""

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.core.database import async_session_factory
from auth.core.security import AESEncryption
from auth.db.models.rbac import Role
from auth.db.models.user import User
from auth.middlewares.tenant import get_session_cookie_name
from auth.services.auth import AuthService
from auth.services.device_code import DeviceCodeService
from auth.services.email import EmailService
from auth.services.jar import JARService
from auth.services.jwks import JWKSService
from auth.services.mfa import MFAService
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.par import PARService
from auth.services.password import PasswordService
from auth.services.pat import PAT_PREFIX, PersonalAccessTokenService
from auth.services.profile import ProfileService
from auth.services.session import SessionService
from auth.services.token import TokenService
from auth.services.token_exchange import TokenExchangeService
from auth.services.trust import TrustPolicyService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

# Bearer scheme for API authentication (auto_error=False to allow cookie fallback)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class BearerTokenAuth:
    """Represents authentication via Bearer token (machine-to-machine).

    Used when a client authenticates via OAuth2 client_credentials flow
    instead of a user session cookie.
    """

    client_id: str
    scopes: list[str]
    subject: str | None = None  # user_id if token is user-scoped


@dataclass
class PATAuth:
    """Represents authentication via Personal Access Token.

    Used when a user authenticates via PAT instead of session or OAuth2 token.
    """

    user_id: str
    pat_id: str
    scopes: list[str]
    tenant_id: str | None = None
    target_client_id: str | None = None


# Type alias for authentication result (either user session, bearer token, or PAT)
AuthResult = tuple[User, list[Role]] | BearerTokenAuth | PATAuth


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_encryption() -> AESEncryption:
    """Get AES encryption instance (cached)."""
    return AESEncryption.from_base64(settings.jwks_encryption_key)


def get_jwks_service() -> JWKSService:
    """Get JWKS service instance."""
    return JWKSService(get_encryption())


def get_user_service() -> UserService:
    """Get user service instance."""
    return UserService()


def get_email_service() -> EmailService:
    """Get email service instance."""
    return EmailService()


def get_password_service() -> PasswordService:
    """Get password service instance."""
    return PasswordService()


def get_auth_service() -> AuthService:
    """Get auth service instance."""
    return AuthService()


def get_session_service() -> SessionService:
    """Get session service instance."""
    return SessionService()


def get_mfa_service() -> MFAService:
    """Get MFA service instance."""
    return MFAService(get_encryption())


def get_oauth2_client_service() -> OAuth2ClientService:
    """Get OAuth2 client service instance."""
    return OAuth2ClientService()


def get_token_service() -> TokenService:
    """Get token service instance."""
    return TokenService(get_jwks_service())


def get_device_code_service() -> DeviceCodeService:
    """Get device code service instance."""
    return DeviceCodeService()


def get_par_service() -> PARService:
    """Get PAR service instance."""
    return PARService()


def get_jar_service() -> JARService:
    """Get JAR service instance."""
    return JARService()


def get_token_exchange_service() -> TokenExchangeService:
    """Get token exchange service instance."""
    return TokenExchangeService()


def get_profile_service() -> ProfileService:
    """Get profile service instance."""
    return ProfileService()


def get_pat_service() -> PersonalAccessTokenService:
    """Get PAT service instance."""
    return PersonalAccessTokenService()


def get_trust_service() -> TrustPolicyService:
    """Get trust policy service instance."""
    return TrustPolicyService()


def get_pairwise_service():
    """Get pairwise subject service instance."""
    from auth.services.pairwise import PairwiseSubjectService

    return PairwiseSubjectService()


@lru_cache
def get_branding_service():
    """Get branding service instance (cached)."""
    from auth.services.branding import BrandingService

    templates_dir = Path(__file__).parent.parent / "templates"
    return BrandingService(templates_dir, async_session_factory)


@lru_cache
def get_templates() -> Jinja2Templates:
    """Get Jinja2 templates instance (cached)."""
    templates_dir = Path(__file__).parent.parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Get the current authenticated user from session cookie.

    Args:
        request: The HTTP request.
        db: Database session.

    Returns:
        The authenticated user or None if not authenticated.
    """
    session_token = request.cookies.get(get_session_cookie_name())

    if not session_token:
        return None

    # Delegate to SessionService (via SessionRepository) so DI stays out of
    # raw SQL. Expiration check is kept here — the service returns the
    # non-revoked row with ``user`` eager-loaded regardless of expiry.
    session_service = get_session_service()
    session = await session_service.get_session_with_user_by_token(db, session_token)

    if not session:
        return None

    # Check expiration
    if session.expires_at < datetime.now(UTC):
        return None

    return session.user


async def validate_bearer_token(
    request: Request,
    db: AsyncSession,
    credentials: HTTPAuthorizationCredentials | None,
) -> BearerTokenAuth | None:
    """Validate Bearer token and return authentication info.

    The JWT ``sub`` claim is a pairwise identifier (per-tenant).  This function
    resolves it back to the real user_id so callers always receive a usable subject.

    Args:
        request: The HTTP request.
        db: Database session.
        credentials: Bearer token credentials from header.

    Returns:
        BearerTokenAuth if valid token, None otherwise.
    """
    if not credentials:
        return None

    token = credentials.credentials

    try:
        # Decode without verification first to get claims
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.DecodeError:
        logger.debug("Bearer token decode failed")
        return None

    jti = unverified.get("jti")
    if not jti:
        logger.debug("Bearer token missing jti")
        return None

    # Validate token exists and is not revoked in database
    token_service = get_token_service()
    access_token = await token_service.get_access_token_by_jti(db, jti)
    if not access_token:
        logger.debug("Bearer token not found in database: jti=%s", jti)
        return None

    if access_token.revoked_at is not None:
        logger.debug("Bearer token revoked: jti=%s", jti)
        return None

    now = datetime.now(UTC)
    if access_token.expires_at < now:
        logger.debug("Bearer token expired: jti=%s", jti)
        return None

    # Extract scopes from token
    scope_str = unverified.get("scope", "")
    scopes = scope_str.split() if scope_str else []

    subject = unverified.get("sub")

    # Resolve pairwise subject back to real user_id
    if subject:
        subject = await _resolve_pairwise_subject(db, subject, access_token)

    return BearerTokenAuth(
        client_id=unverified.get("client_id", ""),
        scopes=scopes,
        subject=subject,
    )


async def _resolve_pairwise_subject(
    db: AsyncSession,
    subject: str,
    access_token: Any,
) -> str:
    """Resolve a pairwise subject identifier back to the real user_id.

    Falls back to the original subject value when:
    - The access_token has no associated client (should not happen).
    - The pairwise service cannot resolve the sub (old token format).

    Args:
        db: Database session.
        subject: The ``sub`` claim from the JWT.
        access_token: The validated AccessToken row.

    Returns:
        The real user_id as a string, or the original subject as fallback.
    """
    client_service = get_oauth2_client_service()
    client = await client_service.get_by_id(db, access_token.client_id)
    if not client:
        logger.warning(
            "Pairwise resolution skipped: client not found for access_token jti=%s",
            access_token.jti,
        )
        return subject

    pairwise_service = get_pairwise_service()
    real_user_id = await pairwise_service.resolve_user_id_for_client(db, subject, client)
    if real_user_id is not None:
        return str(real_user_id)

    # Backward compatibility: the sub might be a raw user_id from a token
    # issued before pairwise was enabled.
    logger.warning(
        "Pairwise resolution failed for sub=%s, client=%s — "
        "falling back to raw sub (old token format)",
        subject,
        client.client_id,
    )
    return subject


async def validate_pat_token(
    request: Request,
    db: AsyncSession,
    credentials: HTTPAuthorizationCredentials | None,
) -> PATAuth | None:
    """Validate Personal Access Token and return authentication info.

    Args:
        request: The HTTP request.
        db: Database session.
        credentials: Bearer token credentials from header.

    Returns:
        PATAuth if valid PAT, None otherwise.
    """
    if not credentials:
        return None

    token = credentials.credentials

    # Check if this is a PAT (has our prefix)
    if not token.startswith(PAT_PREFIX):
        return None

    pat_service = get_pat_service()
    pat = await pat_service.validate_token(db, token)

    if not pat:
        return None

    # Update usage stats
    client_ip = request.client.host if request.client else None
    await pat_service.update_token_usage(db, pat, client_ip)

    return PATAuth(
        user_id=str(pat.user_id),
        pat_id=str(pat.id),
        scopes=list(pat.scopes),
        tenant_id=str(pat.tenant_id) if pat.tenant_id else None,
        target_client_id=str(pat.target_client_id) if pat.target_client_id else None,
    )


def token_has_scope(scopes: list[str], required_scope: str) -> bool:
    """Check if token scopes include the required scope.

    Supports wildcard matching (e.g., "users:*" matches "users:read").

    Args:
        scopes: List of scopes from the token.
        required_scope: The scope to check for.

    Returns:
        True if the scope is present.
    """
    return any(
        scope == required_scope
        or (scope.endswith(":*") and required_scope.startswith(scope[:-1]))
        or scope == "*"
        for scope in scopes
    )


def user_has_scope(roles: list[Role], required_scope: str) -> bool:
    """Check if user has the required scope through any of their roles.

    Args:
        roles: List of user's roles.
        required_scope: The scope to check for.

    Returns:
        True if user has the scope.
    """
    return any(role.has_scope(required_scope) for role in roles)


def get_user_admin_permissions(roles: list[Role]) -> dict[str, bool]:
    """Get admin permissions for a user based on their roles.

    Args:
        roles: List of user's roles with scopes loaded.

    Returns:
        Dictionary with permission flags for each admin section.
        Includes both legacy can_view_* format and direct scope format (e.g., clients:write).
    """
    return {
        # Legacy format for backward compatibility
        "can_view_dashboard": any(
            user_has_scope(roles, scope)
            for scope in [
                "users:read",
                "clients:read",
                "sessions:read",
                "jwks:read",
                "roles:read",
                "scopes:read",
                "org:read",
                "pats:read",
                "*",
            ]
        ),
        "can_view_jwks": user_has_scope(roles, "jwks:read"),
        "can_view_users": user_has_scope(roles, "users:read"),
        "can_view_clients": user_has_scope(roles, "clients:read"),
        "can_view_sessions": user_has_scope(roles, "sessions:read"),
        "can_view_roles": user_has_scope(roles, "roles:read"),
        "can_view_scopes": user_has_scope(roles, "scopes:read"),
        "can_view_orgs": user_has_scope(roles, "org:read"),
        "can_view_pats": user_has_scope(roles, "pats:read"),
        # Users permissions
        "users:read": user_has_scope(roles, "users:read"),
        "users:write": user_has_scope(roles, "users:write"),
        "users:delete": user_has_scope(roles, "users:delete"),
        "users:disable": user_has_scope(roles, "users:disable"),
        # Clients permissions
        "clients:read": user_has_scope(roles, "clients:read"),
        "clients:write": user_has_scope(roles, "clients:write"),
        "clients:delete": user_has_scope(roles, "clients:delete"),
        "clients:rotate": user_has_scope(roles, "clients:rotate"),
        # Sessions permissions
        "sessions:read": user_has_scope(roles, "sessions:read"),
        "sessions:revoke": user_has_scope(roles, "sessions:revoke"),
        # Roles permissions
        "roles:read": user_has_scope(roles, "roles:read"),
        "roles:write": user_has_scope(roles, "roles:write"),
        "roles:delete": user_has_scope(roles, "roles:delete"),
        "roles:assign": user_has_scope(roles, "roles:assign"),
        # Scopes permissions
        "scopes:read": user_has_scope(roles, "scopes:read"),
        "scopes:write": user_has_scope(roles, "scopes:write"),
        "scopes:delete": user_has_scope(roles, "scopes:delete"),
        # JWKS permissions
        "jwks:read": user_has_scope(roles, "jwks:read"),
        "jwks:write": user_has_scope(roles, "jwks:write"),
        "jwks:delete": user_has_scope(roles, "jwks:delete"),
        "jwks:revoke": user_has_scope(roles, "jwks:revoke"),
        "jwks:rotate": user_has_scope(roles, "jwks:rotate"),
        # Org permissions
        "org:read": user_has_scope(roles, "org:read"),
        "org:write": user_has_scope(roles, "org:write"),
        "org:delete": user_has_scope(roles, "org:delete"),
        # PATs permissions (admin)
        "pats:read": user_has_scope(roles, "pats:read"),
        "pats:revoke": user_has_scope(roles, "pats:revoke"),
    }
