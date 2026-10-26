# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant and multi-tenancy related database models."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.db.base import Base, TimestampMixin


class TenantRole(StrEnum):
    """Role of a user within a tenant.

    DEPRECATED: Use TenantCustomRole for new code. This enum is kept for
    backward compatibility during migration.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


# Tenant-level scopes for custom roles
TENANT_SCOPES = {
    "*": "Full access to all tenant operations",
    # Members
    "members:*": "All member operations",
    "members:read": "View tenant members",
    "members:invite": "Invite new members",
    "members:update": "Update member roles",
    "members:remove": "Remove members from tenant",
    # Settings
    "settings:*": "All settings operations",
    "settings:read": "View tenant settings",
    "settings:write": "Modify tenant settings (name, e-mail sender, allowed scopes, fields)",
    # Custom domain
    "domain:*": "All custom domain operations",
    "domain:read": "View the custom domain and its verification status",
    "domain:write": "Set, remove and verify the custom domain",
    # Roles
    "roles:*": "All role operations",
    "roles:read": "View tenant roles",
    "roles:write": "Create and modify custom roles",
    "roles:delete": "Delete custom roles",
    # Identity Providers
    "idp:*": "All identity provider operations",
    "idp:read": "View identity provider configurations",
    "idp:write": "Configure identity providers",
    "idp:delete": "Delete identity providers",
    # Branding
    "branding:*": "All branding operations",
    "branding:read": "View branding settings",
    "branding:write": "Modify branding (colors, logos, CSS)",
    # Templates
    "templates:*": "All template operations",
    "templates:read": "View custom templates",
    "templates:write": "Modify custom templates",
    # OAuth2 Clients
    "clients:*": "All OAuth2 client operations",
    "clients:read": "View organization's OAuth2 clients",
    "clients:write": "Create and modify OAuth2 clients",
    "clients:delete": "Delete OAuth2 clients",
    "clients:rotate": "Rotate OAuth2 client secrets",
    # Trust Policy
    "trust:*": "All trust policy operations",
    "trust:read": "View trust policy settings",
    "trust:write": "Modify trust policy",
    # Billing (optional, for future)
    "billing:*": "All billing operations",
    "billing:read": "View billing information",
    "billing:write": "Modify billing settings",
    # Webhooks
    "webhooks:*": "All webhook operations",
    "webhooks:read": "View webhook configurations and deliveries",
    "webhooks:write": "Create and modify webhooks",
    "webhooks:delete": "Delete webhooks",
}

# Built-in scopes that are always available in the scope selector,
# regardless of what's in the scopes DB table.
BUILTIN_SCOPES: list[tuple[str, str, str, str]] = [
    # (name, description, category, resource)
    ("openid", "OpenID Connect authentication", "OIDC", "OIDC"),
    ("profile", "User profile information (name, picture, etc.)", "OIDC", "OIDC"),
    ("email", "User email address and verification status", "OIDC", "OIDC"),
    ("offline_access", "Refresh tokens for offline access", "OIDC", "OIDC"),
    ("introspect", "Introspect tokens (RFC 7662)", "System", "System"),
]


def _label(value: str) -> str:
    """Convert a scope category/resource to a display label."""
    value = value.replace("_", " ")
    if len(value) <= 4 and value.isalpha():
        return value.upper()
    return value.title()


def build_scope_groups_from_db(
    scopes: list,
) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """Build scope groups from Scope model instances for UI display.

    Merges DB scopes with built-in OIDC/system scopes.
    Groups by ``category`` then by ``resource``.

    Args:
        scopes: List of Scope model instances (must have name, description, resource, category).

    Returns:
        Ordered dict of category_label -> {resource_label -> [(scope_name, description), ...]}.
    """
    categories: dict[str, dict[str, list[tuple[str, str]]]] = {}
    seen: set[str] = set()

    # Add DB scopes
    for scope in scopes:
        cat = _label(scope.category or "other")
        res = _label(scope.resource or "other")
        description = scope.description or scope.name
        categories.setdefault(cat, {}).setdefault(res, []).append((scope.name, description))
        seen.add(scope.name)

    # Merge built-in scopes (skip if already present from DB)
    for name, description, cat, res in BUILTIN_SCOPES:
        if name not in seen:
            categories.setdefault(cat, {}).setdefault(res, []).append((name, description))

    return {k: dict(sorted(v.items())) for k, v in sorted(categories.items())}


# Default roles created for each new tenant
DEFAULT_TENANT_ROLES = {
    "owner": {
        "display_name": "Owner",
        "description": "Full control over the organization, including managing other owners",
        "scopes": ["*"],
        "is_system": True,
        "display_order": 0,
    },
    "admin": {
        "display_name": "Admin",
        "description": "Can manage members, IdPs, branding, and templates (except owner roles)",
        "scopes": [
            "members:*",
            "settings:read",
            "roles:read",
            "idp:*",
            "branding:*",
            "templates:*",
            "clients:read",
            "trust:read",
            "domain:read",
            "webhooks:*",
        ],
        "is_system": True,
        "display_order": 1,
    },
    "member": {
        "display_name": "Member",
        "description": "Basic access to organization resources",
        "scopes": ["members:read"],
        "is_system": True,
        "display_order": 2,
    },
}


class CustomDomainStatus(StrEnum):
    """Status of custom domain provisioning."""

    PENDING = "pending"  # Domain configured, waiting for DNS verification
    DNS_VERIFYING = "dns_verifying"  # Currently checking DNS
    DNS_VERIFIED = "dns_verified"  # DNS verified, ready for SSL
    SSL_PROVISIONING = "ssl_provisioning"  # Certbot running
    ACTIVE = "active"  # Fully provisioned and working
    FAILED = "failed"  # Provisioning failed (see error message)


class IdentityProviderType(StrEnum):
    """Type of external identity provider."""

    OIDC = "oidc"  # Generic OIDC (Keycloak, Auth0, Okta, Azure AD)
    SAML = "saml"  # SAML 2.0
    GOOGLE = "google"  # Google OAuth2
    GITHUB = "github"  # GitHub OAuth2
    MICROSOFT = "microsoft"  # Microsoft/Azure AD


class TenantTrustMode(StrEnum):
    """Trust mode for external user access.

    Defines how a tenant handles users from other tenants attempting to log in.
    """

    NONE = "none"  # Only users registered on this tenant can login
    ALL = "all"  # Any user can login (open access)
    MEMBERS_ONLY = "members_only"  # Only tenant members can login (regardless of origin)
    SPECIFIC = "specific"  # Only users from specific trusted tenants can login


class Tenant(Base, TimestampMixin):
    """Tenant (organization) for multi-tenancy support."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(
        String(63),  # Max subdomain length
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    custom_domain: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    custom_domain_status: Mapped[CustomDomainStatus | None] = mapped_column(
        Enum(CustomDomainStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
        index=True,
    )
    custom_domain_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    custom_domain_ssl_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    custom_domain_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    custom_domain_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # Platform tenant flag - only one tenant should have this set to True
    # The platform tenant represents the main domain (e.g., auth.example.com)
    is_platform: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    # Settings stored as JSON (branding, policies, MFA requirements, etc.)
    settings: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Trust policy: controls which external users can login to this tenant
    trust_mode: Mapped[TenantTrustMode] = mapped_column(
        Enum(TenantTrustMode, values_callable=lambda obj: [e.value for e in obj]),
        default=TenantTrustMode.NONE,
        nullable=False,
    )

    # Relationships
    members: Mapped[list["TenantMember"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    identity_providers: Mapped[list["IdentityProvider"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    branding: Mapped["TenantBranding | None"] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        uselist=False,
    )
    templates: Mapped[list["TenantTemplate"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    trusted_sources: Mapped[list["TenantTrustedSource"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        foreign_keys="TenantTrustedSource.tenant_id",
    )
    roles: Mapped[list["TenantCustomRole"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    webhooks: Mapped[list["TenantWebhook"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Tenant slug={self.slug} active={self.is_active}>"


class TenantCustomRole(Base, TimestampMixin):
    """Custom role definition for a tenant with associated scopes.

    Each tenant can have its own set of roles with custom permissions.
    Default system roles (Owner, Admin, Member) are created for each tenant.
    """

    __tablename__ = "tenant_roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_roles_tenant_name"),
        # At most one role per tenant can be the default for self-register /
        # auto-provision. Enforced by a partial unique index (see migration).
        Index(
            "uq_tenant_roles_default",
            "tenant_id",
            unique=True,
            postgresql_where="is_default",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # Scopes stored as ARRAY - e.g., ["members:read", "settings:*"]
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)),
        nullable=False,
        default=list,
    )
    # System roles (owner, admin, member) cannot be deleted
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # Role assigned automatically on self-register / IdP auto-provision.
    # At most one role per tenant may have this flag set.
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # Display order for UI sorting
    display_order: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="roles")
    members: Mapped[list["TenantMember"]] = relationship(back_populates="custom_role")

    def has_scope(self, required_scope: str) -> bool:
        """Check if this role has the required scope.

        Supports wildcard matching:
        - "*" matches everything (full access)
        - "resource:*" matches all actions on that resource
        - Exact match for specific scopes

        Args:
            required_scope: The scope to check (e.g., "members:read")

        Returns:
            True if the role has the required scope.
        """
        if not self.scopes:
            return False

        resource = required_scope.split(":")[0] if ":" in required_scope else required_scope

        for scope in self.scopes:
            # Global wildcard - full access
            if scope == "*":
                return True
            # Exact match
            if scope == required_scope:
                return True
            # Resource wildcard (e.g., "members:*" matches "members:read")
            if scope == f"{resource}:*":
                return True

        return False

    def __repr__(self) -> str:
        return f"<TenantCustomRole tenant_id={self.tenant_id} name={self.name}>"


class TenantMember(Base, TimestampMixin):
    """Membership of a user in a tenant."""

    __tablename__ = "tenant_members"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_members_tenant_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Reference to custom role (required after migration 049)
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant_roles.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    invited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    inviter: Mapped["User | None"] = relationship(foreign_keys=[invited_by])
    custom_role: Mapped["TenantCustomRole | None"] = relationship(back_populates="members")

    @property
    def role_name(self) -> str:
        """Get the role name.

        Returns:
            The name of the custom role, or 'member' as fallback.
        """
        if self.custom_role:
            return self.custom_role.name
        return "member"

    @property
    def role_display_name(self) -> str:
        """Get the display name of the role."""
        if self.custom_role:
            return self.custom_role.display_name
        return "Member"

    def has_scope(self, required_scope: str) -> bool:
        """Check if member has the required scope via their role.

        Args:
            required_scope: The scope to check (e.g., "members:read")

        Returns:
            True if the member's role has the required scope.
        """
        if self.custom_role:
            return self.custom_role.has_scope(required_scope)
        # Fallback if custom_role not loaded - assume basic read access
        return required_scope == "members:read"

    def __repr__(self) -> str:
        return (
            f"<TenantMember tenant_id={self.tenant_id} "
            f"user_id={self.user_id} "
            f"role={self.role_name}>"
        )


class IdentityProvider(Base, TimestampMixin):
    """External identity provider configuration for a tenant."""

    __tablename__ = "identity_providers"
    __table_args__ = (Index("ix_identity_providers_tenant_active", "tenant_id", "is_active"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    provider_type: Mapped[IdentityProviderType] = mapped_column(
        Enum(IdentityProviderType),
        nullable=False,
    )

    # OIDC Configuration
    discovery_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    authorization_endpoint: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    token_endpoint: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    userinfo_endpoint: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    jwks_uri: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    # Client credentials
    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    client_secret_encrypted: Mapped[bytes | None] = mapped_column(
        nullable=True,
    )

    # Scopes to request from the IdP
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=["openid", "profile", "email"],
    )

    # Attribute mapping: external claim name -> internal field name
    # e.g., {"email": "mail", "name": "displayName", "given_name": "firstName"}
    attribute_mapping: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Domain restrictions for this IdP (e.g., ["acme.com", "acme.org"])
    allowed_domains: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    # Settings
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    auto_provision: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # Allow users to link existing accounts with this IdP
    allow_linking: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Display settings
    icon_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    button_text: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    display_order: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="identity_providers")
    federated_identities: Mapped[list["FederatedIdentity"]] = relationship(
        back_populates="identity_provider",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<IdentityProvider name={self.name} "
            f"type={self.provider_type} "
            f"tenant_id={self.tenant_id}>"
        )


class TenantBranding(Base, TimestampMixin):
    """Branding and theming configuration for a tenant."""

    __tablename__ = "tenant_branding"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Logo and favicon
    logo_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    logo_dark_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    favicon_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    # Colors
    primary_color: Mapped[str] = mapped_column(
        String(7),
        default="#007bff",
        nullable=False,
    )
    secondary_color: Mapped[str] = mapped_column(
        String(7),
        default="#6c757d",
        nullable=False,
    )
    accent_color: Mapped[str] = mapped_column(
        String(7),
        default="#28a745",
        nullable=False,
    )
    background_color: Mapped[str] = mapped_column(
        String(7),
        default="#f5f5f5",
        nullable=False,
    )
    surface_color: Mapped[str] = mapped_column(
        String(7),
        default="#ffffff",
        nullable=False,
    )
    text_color: Mapped[str] = mapped_column(
        String(7),
        default="#333333",
        nullable=False,
    )
    text_muted_color: Mapped[str] = mapped_column(
        String(7),
        default="#6c757d",
        nullable=False,
    )
    error_color: Mapped[str] = mapped_column(
        String(7),
        default="#dc3545",
        nullable=False,
    )
    success_color: Mapped[str] = mapped_column(
        String(7),
        default="#28a745",
        nullable=False,
    )
    border_color: Mapped[str] = mapped_column(
        String(7),
        default="#0f3460",
        nullable=False,
    )
    warning_color: Mapped[str] = mapped_column(
        String(7),
        default="#fdcb6e",
        nullable=False,
    )
    info_color: Mapped[str] = mapped_column(
        String(7),
        default="#74b9ff",
        nullable=False,
    )

    # Input-specific colors (nullable = fallback to generic colors)
    input_background_color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
    )
    input_focus_background_color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
    )
    input_border_color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
    )
    input_focus_border_color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
    )
    input_text_color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
    )

    # Typography
    font_family: Mapped[str] = mapped_column(
        String(255),
        default="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        nullable=False,
    )
    font_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    # Custom CSS (appended after theme variables)
    custom_css: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Custom JavaScript (for analytics, etc.)
    custom_js: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Additional settings
    show_powered_by: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="branding")

    def __repr__(self) -> str:
        return f"<TenantBranding tenant_id={self.tenant_id}>"


class TenantTemplate(Base, TimestampMixin):
    """Custom template override for a tenant.

    Allows tenants to customize specific templates (login, register, etc.)
    by storing Jinja2 template content in the database.
    """

    __tablename__ = "tenant_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "template_name", name="uq_tenant_templates_tenant_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Template identifier (e.g., "auth/login.html", "auth/register.html")
    template_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Jinja2 template content
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Is this template active? Allows disabling without deleting
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Description for admin UI
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="templates")

    def __repr__(self) -> str:
        return f"<TenantTemplate tenant_id={self.tenant_id} name={self.template_name}>"


class FederatedIdentity(Base, TimestampMixin):
    """Link between a local user and an external identity from an IdP."""

    __tablename__ = "federated_identities"
    __table_args__ = (
        UniqueConstraint(
            "identity_provider_id", "external_subject", name="uq_federated_identities_idp_subject"
        ),
        Index("ix_federated_identities_user_idp", "user_id", "identity_provider_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identity_provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # External identity information
    external_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    external_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    external_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Raw claims from the IdP for debugging/audit
    raw_claims: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Timestamps
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship()
    identity_provider: Mapped["IdentityProvider"] = relationship(
        back_populates="federated_identities"
    )

    def __repr__(self) -> str:
        return (
            f"<FederatedIdentity user_id={self.user_id} "
            f"idp_id={self.identity_provider_id} "
            f"subject={self.external_subject}>"
        )


class TenantTrustedSource(Base, TimestampMixin):
    """Defines trusted source tenants for a tenant with SPECIFIC trust mode.

    When a tenant has trust_mode=SPECIFIC, only users from tenants listed here
    (or the main domain if trusted_tenant_id is NULL) can log in.
    """

    __tablename__ = "tenant_trusted_sources"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "trusted_tenant_id", name="uq_tenant_trusted_sources_tenant_trusted"
        ),
        # Index for efficient lookup
        Index("ix_tenant_trusted_sources_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The trusted tenant. NULL means "main domain" (users without a registration tenant)
    trusted_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Description for the admin UI
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        back_populates="trusted_sources",
        foreign_keys=[tenant_id],
    )
    trusted_tenant: Mapped["Tenant | None"] = relationship(
        foreign_keys=[trusted_tenant_id],
    )

    def __repr__(self) -> str:
        return (
            f"<TenantTrustedSource "
            f"tenant_id={self.tenant_id} "
            f"trusted_tenant_id={self.trusted_tenant_id}>"
        )


class WebhookEvent(StrEnum):
    """Events that can trigger an outbound webhook.

    Subscriptions support exact match (``user.created``), group wildcards
    (``user.*``) and the global wildcard (``*``).
    """

    # User lifecycle
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_ACTIVATED = "user.activated"
    USER_DEACTIVATED = "user.deactivated"
    USER_EMAIL_VERIFIED = "user.email_verified"
    USER_EMAIL_CHANGED = "user.email_changed"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_PASSWORD_RESET_REQUESTED = "user.password_reset_requested"
    USER_PASSWORD_RESET_COMPLETED = "user.password_reset_completed"

    # Authentication
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILED = "login.failed"
    LOGOUT = "logout"
    SESSION_CREATED = "session.created"
    SESSION_REVOKED = "session.revoked"
    SESSION_EXPIRED = "session.expired"

    # MFA
    MFA_ENABLED = "mfa.enabled"
    MFA_DISABLED = "mfa.disabled"
    MFA_CHALLENGE_SUCCESS = "mfa.challenge.success"
    MFA_CHALLENGE_FAILED = "mfa.challenge.failed"
    MFA_BACKUP_CODES_GENERATED = "mfa.backup_codes.generated"
    MFA_BACKUP_CODE_USED = "mfa.backup_codes.used"

    # Membership
    MEMBER_INVITED = "member.invited"
    MEMBER_INVITE_ACCEPTED = "member.invite_accepted"
    MEMBER_INVITE_REVOKED = "member.invite_revoked"
    MEMBER_ADDED = "member.added"
    MEMBER_REMOVED = "member.removed"
    MEMBER_LEFT = "member.left"
    MEMBER_ROLE_CHANGED = "member.role_changed"

    # OAuth2 / OIDC
    OAUTH2_AUTHORIZATION_GRANTED = "oauth2.authorization.granted"
    OAUTH2_AUTHORIZATION_DENIED = "oauth2.authorization.denied"
    OAUTH2_TOKEN_ISSUED = "oauth2.token.issued"
    OAUTH2_TOKEN_REVOKED = "oauth2.token.revoked"
    OAUTH2_CONSENT_GRANTED = "oauth2.consent.granted"
    OAUTH2_CONSENT_REVOKED = "oauth2.consent.revoked"
    OAUTH2_DEVICE_CODE_REQUESTED = "oauth2.device_code.requested"
    OAUTH2_DEVICE_CODE_APPROVED = "oauth2.device_code.approved"

    # OAuth2 clients
    CLIENT_CREATED = "client.created"
    CLIENT_UPDATED = "client.updated"
    CLIENT_DELETED = "client.deleted"
    CLIENT_SECRET_ROTATED = "client.secret_rotated"
    CLIENT_SCOPES_CHANGED = "client.scopes_changed"

    # Identity providers / federation
    IDP_CREATED = "idp.created"
    IDP_UPDATED = "idp.updated"
    IDP_DELETED = "idp.deleted"
    IDP_LINKED = "idp.linked"
    IDP_UNLINKED = "idp.unlinked"

    # Personal access tokens
    PAT_CREATED = "pat.created"
    PAT_REVOKED = "pat.revoked"

    # Roles / RBAC
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"

    # Tenant / org
    TENANT_UPDATED = "tenant.updated"
    TENANT_BRANDING_CHANGED = "tenant.branding.changed"
    TENANT_TEMPLATE_CHANGED = "tenant.template.changed"
    TENANT_DOMAIN_ADDED = "tenant.domain.added"
    TENANT_DOMAIN_VERIFIED = "tenant.domain.verified"
    TENANT_DOMAIN_FAILED = "tenant.domain.failed"
    TENANT_TRUST_CHANGED = "tenant.trust.changed"

    # Security
    SECURITY_SUSPICIOUS_LOGIN = "security.suspicious_login"
    SECURITY_ACCOUNT_LOCKED = "security.account.locked"
    SECURITY_ACCOUNT_UNLOCKED = "security.account.unlocked"

    # Webhook meta (fired by the webhook subsystem itself)
    WEBHOOK_TEST = "webhook.test"


class WebhookDeliveryStatus(StrEnum):
    """Lifecycle status of a single webhook delivery attempt chain."""

    PENDING = "pending"  # Queued, not attempted yet
    SUCCESS = "success"  # 2xx received on an attempt
    FAILED = "failed"  # Non-2xx after max_attempts
    RETRYING = "retrying"  # Non-2xx, another attempt scheduled


class TenantWebhook(Base, TimestampMixin):
    """Outbound webhook subscription scoped to a tenant."""

    __tablename__ = "tenant_webhooks"
    __table_args__ = (
        Index("ix_tenant_webhooks_tenant_id", "tenant_id"),
        Index("ix_tenant_webhooks_events", "events", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Subscribed events. Supports exact (``user.created``), group (``user.*``),
    # or global wildcard (``*``).
    events: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    # HMAC-SHA256 secret for signing request bodies.
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    # Extra headers merged with the standard X-Webhook-* set at delivery time.
    headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Lightweight stats mirrored from the latest delivery for quick UI display.
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_code: Mapped[int | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_count: Mapped[int] = mapped_column(default=0, nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="webhooks")
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="webhook",
        cascade="all, delete-orphan",
        order_by="desc(WebhookDelivery.created_at)",
    )

    def __repr__(self) -> str:
        return f"<TenantWebhook id={self.id} tenant_id={self.tenant_id} url={self.url}>"


class WebhookDelivery(Base, TimestampMixin):
    """Record of a webhook delivery attempt chain for a given event.

    A single row covers all retries for one original event. ``attempt`` is the
    number of attempts already made. The full request/response pair of the
    latest attempt is stored for debugging and replay.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index(
            "ix_webhook_deliveries_webhook_created",
            "webhook_id",
            "created_at",
        ),
        Index(
            "ix_webhook_deliveries_tenant_created",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_webhook_deliveries_retry",
            "status",
            "next_retry_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant_webhooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Request snapshot
    request_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    request_headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_body: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Lifecycle
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(WebhookDeliveryStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=WebhookDeliveryStatus.PENDING,
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Response snapshot (latest attempt)
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    response_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    webhook: Mapped["TenantWebhook"] = relationship(back_populates="deliveries")

    def __repr__(self) -> str:
        return (
            f"<WebhookDelivery id={self.id} event={self.event} "
            f"status={self.status} attempt={self.attempt}/{self.max_attempts}>"
        )


if TYPE_CHECKING:
    from auth.db.models.user import User
