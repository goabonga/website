# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SQLAlchemy models."""

from knowledge.models.base import Base
from knowledge.models.collection import Collection
from knowledge.models.collection_collaborator import CollectionCollaborator
from knowledge.models.collection_invitation import CollectionInvitation
from knowledge.models.document import Document
from knowledge.models.enums import (
    CollaboratorPermission,
    InvitationStatus,
    OrganizationMemberRole,
    OwnerType,
    PlanType,
    Platform,
    ReleaseStatus,
)
from knowledge.models.mcp_release import McpRelease, McpReleaseAsset
from knowledge.models.organization import Organization, Tenant
from knowledge.models.organization_invitation import Invitation, OrganizationInvitation
from knowledge.models.organization_member import (
    OrganizationMember,
    TenantMember,
    TenantMemberRole,
)
from knowledge.models.usage import UsageRecord
from knowledge.models.user_plan import UserPlan
from knowledge.models.workspace_deletion_request import (
    DeletionRequestStatus,
    WorkspaceDeletionRequest,
)

__all__ = [
    # Base
    "Base",
    # Enums
    "CollaboratorPermission",
    "InvitationStatus",
    "OrganizationMemberRole",
    "OwnerType",
    "PlanType",
    "Platform",
    "ReleaseStatus",
    # Core models
    "Collection",
    "CollectionCollaborator",
    "CollectionInvitation",
    "Document",
    "McpRelease",
    "McpReleaseAsset",
    "Organization",
    "OrganizationInvitation",
    "OrganizationMember",
    "UsageRecord",
    "UserPlan",
    "WorkspaceDeletionRequest",
    "DeletionRequestStatus",
    # Backward compatibility aliases
    "Invitation",
    "Tenant",
    "TenantMember",
    "TenantMemberRole",
]
