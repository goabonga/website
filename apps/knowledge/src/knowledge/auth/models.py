# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User model from JWT claims."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class User(BaseModel):
    """User extracted from JWT claims."""

    id: UUID
    email: str | None = None
    name: str | None = None
    nickname: str | None = None
    scopes: list[str] = Field(default_factory=list)

    @property
    def display_name(self) -> str | None:
        """Return nickname if set, otherwise name."""
        return self.nickname or self.name

    @classmethod
    def from_jwt_claims(cls, claims: dict) -> "User":
        """Create User from OIDC/OAuth2 JWT claims.

        Args:
            claims: JWT payload claims.

        Returns:
            User instance.
        """
        # Handle scope as string or list
        scope_claim = claims.get("scope", "")
        if isinstance(scope_claim, str):
            scopes = scope_claim.split() if scope_claim else []
        else:
            scopes = list(scope_claim)

        return cls(
            id=UUID(claims["sub"]),
            email=claims.get("email"),
            name=(
                claims.get("name")
                or claims.get("displayName")
                or claims.get("display_name")
                or claims.get("given_name")
            ),
            nickname=claims.get("nickname") or claims.get("preferred_username"),
            scopes=scopes,
        )

    def has_scope(self, required_scope: str) -> bool:
        """Check if user has a specific scope.

        Supports wildcard matching:
        - "*" matches everything
        - "api:*" matches "api:read", "api:write", etc.
        - "api:read" matches exactly

        Args:
            required_scope: The scope to check.

        Returns:
            True if user has the scope.
        """
        if "*" in self.scopes:
            return True

        if required_scope in self.scopes:
            return True

        # Check wildcard patterns like "knowledge:*"
        scope_parts = required_scope.split(":")
        if len(scope_parts) >= 2:
            # Check for "knowledge:*" matching "knowledge:read"
            for user_scope in self.scopes:
                if user_scope.endswith(":*"):
                    prefix = user_scope[:-1]  # "knowledge:"
                    if required_scope.startswith(prefix):
                        return True

        return False

    def require_scope(self, required_scope: str) -> None:
        """Require a scope, raising 403 if not present.

        Args:
            required_scope: The scope to require.

        Raises:
            HTTPException: 403 if scope is missing.
        """
        from fastapi import HTTPException, status

        if not self.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}",
            )

    def can_read(self, resource: str) -> bool:
        """Check if user can read a resource."""
        return self.has_scope(f"{resource}:read")

    def can_write(self, resource: str) -> bool:
        """Check if user can write a resource."""
        return self.has_scope(f"{resource}:write")

    def can_delete(self, resource: str) -> bool:
        """Check if user can delete a resource."""
        return self.has_scope(f"{resource}:delete") or self.has_scope(f"{resource}:write")


class WebAuthContext(BaseModel):
    """Web authentication context with tenant resolution.

    Used for web pages that need both user and tenant context.
    """

    model_config = {"arbitrary_types_allowed": True}

    user: User
    tenant: Any = None  # Organization model (SQLAlchemy)
    tenant_member: Any = None  # OrganizationMember model (SQLAlchemy)

    @property
    def user_id(self) -> UUID:
        """Get user ID."""
        return self.user.id

    @property
    def tenant_id(self) -> UUID:
        """Get active tenant ID.

        Raises:
            HTTPException: 403 if no active tenant.
        """
        from fastapi import HTTPException, status

        if not self.tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active tenant. Please select a tenant.",
            )
        return self.tenant.id

    @property
    def scopes(self) -> list[str]:
        """Get user scopes."""
        return self.user.scopes

    def has_scope(self, scope: str) -> bool:
        """Check if user has a specific scope."""
        return self.user.has_scope(scope)

    def require_scope(self, scope: str) -> None:
        """Require a specific scope."""
        self.user.require_scope(scope)

    @property
    def is_tenant_owner(self) -> bool:
        """Check if user is the tenant owner."""
        if not self.tenant_member:
            return False
        return self.tenant_member.is_owner

    @property
    def is_tenant_admin(self) -> bool:
        """Check if user is a tenant admin (owner or admin)."""
        if not self.tenant_member:
            return False
        return self.tenant_member.is_admin

    @property
    def can_manage_members(self) -> bool:
        """Check if user can manage tenant members."""
        if not self.tenant_member:
            return False
        return self.tenant_member.can_manage_members

    @property
    def can_manage_tenant(self) -> bool:
        """Check if user can manage tenant settings."""
        if not self.tenant_member:
            return False
        return self.tenant_member.can_manage_tenant

    def require_tenant_admin(self) -> None:
        """Require tenant admin privileges.

        Raises:
            HTTPException: 403 if not admin.
        """
        from fastapi import HTTPException, status

        if not self.is_tenant_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant admin privileges required.",
            )
