# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared enums for the Knowledge API models."""

import enum


class PlanType(enum.StrEnum):
    """Subscription plan types."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OwnerType(enum.StrEnum):
    """Type of entity that owns a collection."""

    USER = "user"
    ORGANIZATION = "organization"


class CollaboratorPermission(enum.StrEnum):
    """Permission level for collection collaborators."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class OrganizationMemberRole(enum.StrEnum):
    """Role of a member within an organization."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class InvitationStatus(enum.StrEnum):
    """Status of an invitation."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CustomDomainStatus(enum.StrEnum):
    """Status of custom domain provisioning."""

    PENDING = "pending"
    DNS_VERIFYING = "dns_verifying"
    DNS_VERIFIED = "dns_verified"
    SSL_PROVISIONING = "ssl_provisioning"
    ACTIVE = "active"
    FAILED = "failed"


class ReleaseStatus(enum.StrEnum):
    """Status of an MCP release."""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class Platform(enum.StrEnum):
    """Supported platforms for MCP binaries."""

    LINUX_X86_64 = "linux-x86_64"
    LINUX_ARM64 = "linux-arm64"
    MACOS_X86_64 = "macos-x86_64"
    MACOS_ARM64 = "macos-arm64"
    WINDOWS_X86_64 = "windows-x86_64"
