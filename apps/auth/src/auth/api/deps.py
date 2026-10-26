# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI dependencies for dependency injection."""

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fastapi.security import HTTPBearer
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.core.database import async_session_factory
from auth.core.security import AESEncryption
from auth.db.models.rbac import Role
from auth.db.models.user import User
from auth.services.email import EmailService
from auth.services.jwks import JWKSService
from auth.services.password import PasswordService
from auth.services.profile import ProfileService
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


def get_profile_service() -> ProfileService:
    """Get profile service instance."""
    return ProfileService()


def get_trust_service() -> TrustPolicyService:
    """Get trust policy service instance."""
    return TrustPolicyService()


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
