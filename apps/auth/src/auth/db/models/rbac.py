# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""RBAC (Role-Based Access Control) database models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.db.base import Base, TimestampMixin


class Scope(Base, TimestampMixin):
    """Permission scope definition.

    Scopes follow the pattern: resource:action
    Examples: users:read, clients:write, api:products:read

    Categories:
    - admin: Admin panel permissions (users, clients, sessions, jwks, roles)
    - api: API-specific permissions for external applications
    - custom: User-defined permissions
    """

    __tablename__ = "scopes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    resource: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="admin",
        index=True,
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    role_scopes: Mapped[list["RoleScope"]] = relationship(
        back_populates="scope",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Scope name={self.name} category={self.category}>"


class Role(Base, TimestampMixin):
    """Role definition with associated scopes.

    Roles group scopes together for easier assignment.
    All scopes (including wildcards) are stored via role_scopes relationship.

    Wildcard scopes in database:
    - * = super admin (all permissions)
    - users:* = all user permissions
    - clients:* = all client permissions
    - etc.
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    role_scopes: Mapped[list["RoleScope"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Role name={self.name}>"

    def has_scope(self, required_scope: str) -> bool:
        """Check if role has the required scope.

        All scopes are stored via role_scopes relationship.

        Supports wildcard matching:
        - "*" matches everything
        - "users:*" matches "users:read", "users:write", etc.
        """
        resource = required_scope.split(":")[0]

        for rs in self.role_scopes:
            if not rs.scope or not rs.scope.is_active:
                continue

            scope_name = rs.scope.name

            # Global wildcard
            if scope_name == "*":
                return True

            # Exact match
            if scope_name == required_scope:
                return True

            # Resource wildcard match (e.g., "users:*" matches "users:read")
            if scope_name == f"{resource}:*":
                return True

        return False

    def get_all_scope_names(self) -> list[str]:
        """Get all scope names from role_scopes relationship."""
        scope_names = []
        for rs in self.role_scopes:
            if rs.scope and rs.scope.is_active:
                scope_names.append(rs.scope.name)
        return scope_names


class RoleScope(Base, TimestampMixin):
    """Association between roles and scopes."""

    __tablename__ = "role_scopes"
    __table_args__ = (
        UniqueConstraint("role_id", "scope_id", name="uq_role_scopes_role_id_scope_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scopes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    role: Mapped["Role"] = relationship(back_populates="role_scopes")
    scope: Mapped["Scope"] = relationship(back_populates="role_scopes")

    def __repr__(self) -> str:
        return f"<RoleScope role_id={self.role_id} scope_id={self.scope_id}>"


class UserRole(Base, TimestampMixin):
    """Association between users and roles."""

    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    role: Mapped["Role"] = relationship(back_populates="user_roles")

    def __repr__(self) -> str:
        return f"<UserRole user_id={self.user_id} role_id={self.role_id}>"

    @property
    def is_expired(self) -> bool:
        """Check if the role assignment has expired."""
        if self.expires_at is None:
            return False

        return datetime.now(UTC) > self.expires_at


# Scopes of the authorization of auth itself (admin API and console), including wildcards.
# They belong to the behaviour of the service. The scopes of the other services of a
# deployment are not in the code.
ADMIN_SCOPES = {
    # Global wildcard
    "*": "Full access to all operations (super admin)",
    # Users
    "users:*": "All user operations",
    "users:read": "View user information (list, details)",
    "users:write": "Create and update users",
    "users:delete": "Delete users permanently",
    "users:disable": "Enable/disable user accounts",
    # OAuth2 Clients
    "clients:*": "All OAuth2 client operations",
    "clients:read": "View OAuth2 client information",
    "clients:write": "Create and update OAuth2 clients",
    "clients:delete": "Delete OAuth2 clients",
    "clients:rotate": "Rotate OAuth2 client secrets",
    # Sessions
    "sessions:*": "All session operations",
    "sessions:read": "View active sessions",
    "sessions:revoke": "Revoke user sessions",
    # JWKS
    "jwks:*": "All JWKS key operations",
    "jwks:read": "View JWKS keys (public key info)",
    "jwks:write": "Create and activate JWKS keys",
    "jwks:revoke": "Revoke JWKS keys",
    "jwks:delete": "Delete JWKS keys permanently",
    "jwks:rotate": "Rotate JWKS keys automatically",
    # Roles
    "roles:*": "All role operations",
    "roles:read": "View roles and available scopes",
    "roles:write": "Create and update custom roles",
    "roles:delete": "Delete custom roles",
    "roles:assign": "Assign/remove roles to/from users",
    # Scopes
    "scopes:*": "All scope operations",
    "scopes:read": "View available scopes",
    "scopes:write": "Create and update scopes",
    "scopes:delete": "Delete scopes",
    # Organisations (tenants)
    "org:*": "All organisation operations",
    "org:read": "View organisations, their members and identity providers",
    "org:write": "Create and update organisations, their members and identity providers",
    "org:delete": "Delete organisations and identity providers",
    # Personal Access Tokens (admin)
    "pats:*": "All PAT management operations (admin)",
    "pats:read": "View all users' personal access tokens",
    "pats:revoke": "Revoke any user's personal access tokens",
}

# Default system roles with their scope names
DEFAULT_ROLES = {
    "super_admin": {
        "description": "Full access to all admin operations",
        "scopes": ["*"],
        "is_system": True,
    },
    "admin": {
        "description": "Manage users, clients, and sessions",
        "scopes": ["users:*", "clients:*", "sessions:*"],
        "is_system": True,
    },
    "user_manager": {
        "description": "Manage users only",
        "scopes": [
            "users:read",
            "users:write",
            "users:disable",
            "sessions:read",
            "sessions:revoke",
        ],
        "is_system": True,
    },
    "client_manager": {
        "description": "Manage OAuth2 clients",
        "scopes": ["clients:*"],
        "is_system": True,
    },
    "jwks_admin": {
        "description": "Manage JWKS keys",
        "scopes": ["jwks:*"],
        "is_system": True,
    },
    "security_admin": {
        "description": "Security operations (sessions, JWKS)",
        "scopes": ["sessions:*", "jwks:*"],
        "is_system": True,
    },
    "readonly": {
        "description": "Read-only access to all resources",
        "scopes": [
            "users:read",
            "clients:read",
            "sessions:read",
            "jwks:read",
            "roles:read",
            "scopes:read",
        ],
        "is_system": True,
    },
    "operator": {
        "description": "Read access + session revocation",
        "scopes": [
            "users:read",
            "clients:read",
            "sessions:read",
            "sessions:revoke",
        ],
        "is_system": True,
    },
}
