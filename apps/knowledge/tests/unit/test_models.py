# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for model properties and methods.

Tests all @property, @classmethod, and instance methods on SQLAlchemy models
that are not covered by existing tests. Instantiates models via their
normal SQLAlchemy constructor (passing keyword arguments) so that the
instrumented attributes are initialised correctly.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from knowledge.models.collection import Collection
from knowledge.models.collection_collaborator import CollectionCollaborator
from knowledge.models.collection_invitation import CollectionInvitation
from knowledge.models.enums import (
    CollaboratorPermission,
    CustomDomainStatus,
    InvitationStatus,
    OrganizationMemberRole,
    OwnerType,
    PlanType,
)
from knowledge.models.organization import Organization
from knowledge.models.organization_invitation import OrganizationInvitation
from knowledge.models.organization_member import OrganizationMember
from knowledge.models.workspace_deletion_request import (
    DeletionRequestStatus,
    WorkspaceDeletionRequest,
)

# ---------------------------------------------------------------------------
# Helper: create a model instance via the standard SQLAlchemy __init__
# ---------------------------------------------------------------------------


def _make(model_cls, **attrs):
    """Create a model instance using its SQLAlchemy-provided __init__.

    This properly sets up _sa_instance_state so that instrumented
    descriptors, @property methods, and attribute access all work.
    """
    return model_cls(**attrs)


# ===================================================================
# Collection model (lines 125, 130, 136, 141)
# ===================================================================


class TestCollectionProperties:
    """Test Collection.is_personal, is_organization_owned, tenant, tenant_id."""

    def test_is_personal_true(self):
        coll = _make(Collection, owner_type=OwnerType.USER)
        assert coll.is_personal is True

    def test_is_personal_false(self):
        coll = _make(Collection, owner_type=OwnerType.ORGANIZATION)
        assert coll.is_personal is False

    def test_is_organization_owned_true(self):
        coll = _make(Collection, owner_type=OwnerType.ORGANIZATION)
        assert coll.is_organization_owned is True

    def test_is_organization_owned_false(self):
        coll = _make(Collection, owner_type=OwnerType.USER)
        assert coll.is_organization_owned is False

    def test_tenant_alias_returns_organization(self):
        org_mock = MagicMock()
        coll = _make(Collection, organization=org_mock)
        assert coll.tenant is org_mock

    def test_tenant_alias_returns_none(self):
        coll = _make(Collection, organization=None)
        assert coll.tenant is None

    def test_tenant_id_alias_returns_organization_id(self):
        uid = uuid4()
        coll = _make(Collection, organization_id=uid)
        assert coll.tenant_id == uid

    def test_tenant_id_alias_returns_none(self):
        coll = _make(Collection, organization_id=None)
        assert coll.tenant_id is None


# ===================================================================
# CollectionCollaborator model (lines 86, 91, 99, 104)
# ===================================================================


class TestCollectionCollaboratorProperties:
    """Test can_read, can_write, can_admin, can_invite."""

    def test_can_read_always_true(self):
        for perm in CollaboratorPermission:
            collab = _make(CollectionCollaborator, permission=perm)
            assert collab.can_read is True

    def test_can_write_with_write(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.WRITE)
        assert collab.can_write is True

    def test_can_write_with_admin(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.ADMIN)
        assert collab.can_write is True

    def test_can_write_with_read(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.READ)
        assert collab.can_write is False

    def test_can_admin_true(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.ADMIN)
        assert collab.can_admin is True

    def test_can_admin_false_write(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.WRITE)
        assert collab.can_admin is False

    def test_can_admin_false_read(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.READ)
        assert collab.can_admin is False

    def test_can_invite_true(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.ADMIN)
        assert collab.can_invite is True

    def test_can_invite_false(self):
        collab = _make(CollectionCollaborator, permission=CollaboratorPermission.READ)
        assert collab.can_invite is False


# ===================================================================
# CollectionInvitation model (lines 106, 111, 116, 121-123, 128-130,
#                              134-136, 140, 144)
# ===================================================================


class TestCollectionInvitationClassMethods:
    """Test generate_token and default_expiry."""

    def test_generate_token_returns_string(self):
        token = CollectionInvitation.generate_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_token_unique(self):
        t1 = CollectionInvitation.generate_token()
        t2 = CollectionInvitation.generate_token()
        assert t1 != t2

    def test_default_expiry_is_future(self):
        exp = CollectionInvitation.default_expiry()
        assert exp > datetime.now(UTC)
        # Should be roughly 7 days in the future
        assert exp < datetime.now(UTC) + timedelta(days=8)


class TestCollectionInvitationProperties:
    """Test is_pending, is_expired, is_valid."""

    def test_is_pending_true(self):
        inv = _make(CollectionInvitation, status=InvitationStatus.PENDING)
        assert inv.is_pending is True

    def test_is_pending_false(self):
        inv = _make(CollectionInvitation, status=InvitationStatus.ACCEPTED)
        assert inv.is_pending is False

    def test_is_expired_status_expired(self):
        inv = _make(
            CollectionInvitation,
            status=InvitationStatus.EXPIRED,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_expired is True

    def test_is_expired_by_time(self):
        inv = _make(
            CollectionInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert inv.is_expired is True

    def test_is_expired_false(self):
        inv = _make(
            CollectionInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_expired is False

    def test_is_valid_true(self):
        inv = _make(
            CollectionInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_valid is True

    def test_is_valid_false_not_pending(self):
        inv = _make(
            CollectionInvitation,
            status=InvitationStatus.ACCEPTED,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_valid is False

    def test_is_valid_false_expired(self):
        inv = _make(
            CollectionInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert inv.is_valid is False


class TestCollectionInvitationMutations:
    """Test accept, revoke, mark_expired."""

    def test_accept(self):
        uid = uuid4()
        inv = _make(
            CollectionInvitation,
            status=InvitationStatus.PENDING,
            accepted_at=None,
            accepted_by=None,
        )
        inv.accept(uid)
        assert inv.status == InvitationStatus.ACCEPTED
        assert inv.accepted_at is not None
        assert inv.accepted_by == uid

    def test_revoke(self):
        inv = _make(CollectionInvitation, status=InvitationStatus.PENDING)
        inv.revoke()
        assert inv.status == InvitationStatus.REVOKED

    def test_mark_expired(self):
        inv = _make(CollectionInvitation, status=InvitationStatus.PENDING)
        inv.mark_expired()
        assert inv.status == InvitationStatus.EXPIRED


# ===================================================================
# Organization model (lines 116, 121, 126, 131, 136)
# ===================================================================


class TestOrganizationProperties:
    """Test allow_member_create_collections, is_enterprise,
    can_use_custom_domain, custom_domain_is_active."""

    def test_allow_member_create_collections_default_true(self):
        org = _make(Organization, settings={})
        assert org.allow_member_create_collections is True

    def test_allow_member_create_collections_explicit_true(self):
        org = _make(Organization, settings={"allow_member_create_collections": True})
        assert org.allow_member_create_collections is True

    def test_allow_member_create_collections_explicit_false(self):
        org = _make(Organization, settings={"allow_member_create_collections": False})
        assert org.allow_member_create_collections is False

    def test_allow_member_create_collections_setter(self):
        org = _make(Organization, settings={"existing_key": "value"})
        org.allow_member_create_collections = False
        assert org.settings["allow_member_create_collections"] is False
        # Existing settings should be preserved
        assert org.settings["existing_key"] == "value"

    def test_is_enterprise_true(self):
        org = _make(Organization, plan=PlanType.ENTERPRISE)
        assert org.is_enterprise is True

    def test_is_enterprise_false(self):
        org = _make(Organization, plan=PlanType.FREE)
        assert org.is_enterprise is False

    def test_can_use_custom_domain_enterprise(self):
        org = _make(Organization, plan=PlanType.ENTERPRISE)
        assert org.can_use_custom_domain is True

    def test_can_use_custom_domain_free(self):
        org = _make(Organization, plan=PlanType.FREE)
        assert org.can_use_custom_domain is False

    def test_custom_domain_is_active_true(self):
        org = _make(
            Organization,
            custom_domain="example.com",
            custom_domain_status=CustomDomainStatus.ACTIVE,
        )
        assert org.custom_domain_is_active is True

    def test_custom_domain_is_active_false_no_domain(self):
        org = _make(
            Organization,
            custom_domain=None,
            custom_domain_status=CustomDomainStatus.ACTIVE,
        )
        assert org.custom_domain_is_active is False

    def test_custom_domain_is_active_false_not_active(self):
        org = _make(
            Organization,
            custom_domain="example.com",
            custom_domain_status=CustomDomainStatus.PENDING,
        )
        assert org.custom_domain_is_active is False


# ===================================================================
# OrganizationInvitation model (lines 108, 113, 118, 123-125, 130,
#                                134-136, 140, 144)
# ===================================================================


class TestOrgInvitationClassMethods:
    """Test generate_token and default_expiry."""

    def test_generate_token_returns_string(self):
        token = OrganizationInvitation.generate_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_default_expiry_is_future(self):
        exp = OrganizationInvitation.default_expiry()
        assert exp > datetime.now(UTC)
        assert exp < datetime.now(UTC) + timedelta(days=8)


class TestOrgInvitationProperties:
    """Test is_pending, is_expired, is_valid."""

    def test_is_pending_true(self):
        inv = _make(OrganizationInvitation, status=InvitationStatus.PENDING)
        assert inv.is_pending is True

    def test_is_pending_false(self):
        inv = _make(OrganizationInvitation, status=InvitationStatus.ACCEPTED)
        assert inv.is_pending is False

    def test_is_expired_status_expired(self):
        inv = _make(
            OrganizationInvitation,
            status=InvitationStatus.EXPIRED,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_expired is True

    def test_is_expired_by_time(self):
        inv = _make(
            OrganizationInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert inv.is_expired is True

    def test_is_expired_false(self):
        inv = _make(
            OrganizationInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_expired is False

    def test_is_valid_true(self):
        inv = _make(
            OrganizationInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_valid is True

    def test_is_valid_false_not_pending(self):
        inv = _make(
            OrganizationInvitation,
            status=InvitationStatus.ACCEPTED,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert inv.is_valid is False

    def test_is_valid_false_expired(self):
        inv = _make(
            OrganizationInvitation,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert inv.is_valid is False


class TestOrgInvitationMutations:
    """Test accept, revoke, mark_expired."""

    def test_accept(self):
        uid = uuid4()
        inv = _make(
            OrganizationInvitation,
            status=InvitationStatus.PENDING,
            accepted_at=None,
            accepted_by=None,
        )
        inv.accept(uid)
        assert inv.status == InvitationStatus.ACCEPTED
        assert inv.accepted_at is not None
        assert inv.accepted_by == uid

    def test_revoke(self):
        inv = _make(OrganizationInvitation, status=InvitationStatus.PENDING)
        inv.revoke()
        assert inv.status == InvitationStatus.REVOKED

    def test_mark_expired(self):
        inv = _make(OrganizationInvitation, status=InvitationStatus.PENDING)
        inv.mark_expired()
        assert inv.status == InvitationStatus.EXPIRED


# ===================================================================
# OrganizationMember model (lines 85, 90, 95, 100, 105, 114-117)
# ===================================================================


class TestOrganizationMemberProperties:
    """Test is_owner, is_admin, can_manage_members, can_manage_organization,
    can_delete_organization, can_create_collections."""

    def test_is_owner_true(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.OWNER)
        assert m.is_owner is True

    def test_is_owner_false_admin(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.ADMIN)
        assert m.is_owner is False

    def test_is_owner_false_member(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.MEMBER)
        assert m.is_owner is False

    def test_is_admin_true_owner(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.OWNER)
        assert m.is_admin is True

    def test_is_admin_true_admin(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.ADMIN)
        assert m.is_admin is True

    def test_is_admin_false_member(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.MEMBER)
        assert m.is_admin is False

    def test_can_manage_members_owner(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.OWNER)
        assert m.can_manage_members is True

    def test_can_manage_members_admin(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.ADMIN)
        assert m.can_manage_members is True

    def test_can_manage_members_member(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.MEMBER)
        assert m.can_manage_members is False

    def test_can_manage_organization_owner(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.OWNER)
        assert m.can_manage_organization is True

    def test_can_manage_organization_member(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.MEMBER)
        assert m.can_manage_organization is False

    def test_can_delete_organization_owner(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.OWNER)
        assert m.can_delete_organization is True

    def test_can_delete_organization_admin(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.ADMIN)
        assert m.can_delete_organization is False

    def test_can_delete_organization_member(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.MEMBER)
        assert m.can_delete_organization is False

    def test_can_create_collections_admin(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.ADMIN)
        assert m.can_create_collections is True

    def test_can_create_collections_owner(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.OWNER)
        assert m.can_create_collections is True

    def test_can_create_collections_member(self):
        m = _make(OrganizationMember, role=OrganizationMemberRole.MEMBER)
        # Member defaults to True (actual check happens in service layer)
        assert m.can_create_collections is True


# ===================================================================
# WorkspaceDeletionRequest model (lines 117, 122, 127, 132-134, 139,
#   144, 149-151, 155-156, 160-165, 170-176, 180, 184, 188, 192)
# ===================================================================


class TestWorkspaceDeletionRequestClassMethods:
    """Test generate_token and default_expiry."""

    def test_generate_token_returns_string(self):
        token = WorkspaceDeletionRequest.generate_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_default_expiry_is_future(self):
        exp = WorkspaceDeletionRequest.default_expiry()
        assert exp > datetime.now(UTC)
        assert exp < datetime.now(UTC) + timedelta(hours=25)


class TestWorkspaceDeletionRequestProperties:
    """Test is_pending, is_expired, is_valid, is_scheduled, is_ready_to_delete,
    needs_reminder."""

    def test_is_pending_true(self):
        req = _make(WorkspaceDeletionRequest, status=DeletionRequestStatus.PENDING)
        assert req.is_pending is True

    def test_is_pending_false(self):
        req = _make(WorkspaceDeletionRequest, status=DeletionRequestStatus.CONFIRMED)
        assert req.is_pending is False

    def test_is_expired_status_expired(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.EXPIRED,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert req.is_expired is True

    def test_is_expired_by_time(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert req.is_expired is True

    def test_is_expired_false(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert req.is_expired is False

    def test_is_valid_true(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert req.is_valid is True

    def test_is_valid_false_not_pending(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.CONFIRMED,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert req.is_valid is False

    def test_is_valid_false_expired(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert req.is_valid is False

    def test_is_scheduled_true(self):
        req = _make(WorkspaceDeletionRequest, status=DeletionRequestStatus.SCHEDULED)
        assert req.is_scheduled is True

    def test_is_scheduled_false(self):
        req = _make(WorkspaceDeletionRequest, status=DeletionRequestStatus.PENDING)
        assert req.is_scheduled is False

    def test_is_ready_to_delete_true(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
            scheduled_deletion_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert req.is_ready_to_delete is True

    def test_is_ready_to_delete_false_not_scheduled(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            scheduled_deletion_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert req.is_ready_to_delete is False

    def test_is_ready_to_delete_false_no_date(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
            scheduled_deletion_at=None,
        )
        assert req.is_ready_to_delete is False

    def test_is_ready_to_delete_false_future(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
            scheduled_deletion_at=datetime.now(UTC) + timedelta(days=5),
        )
        assert req.is_ready_to_delete is False

    def test_needs_reminder_true(self):
        # Deletion is scheduled for tomorrow's half-day from now, and
        # we are within the 1-day reminder threshold
        deletion_at = datetime.now(UTC) + timedelta(hours=12)
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
            scheduled_deletion_at=deletion_at,
            reminder_sent_at=None,
        )
        assert req.needs_reminder is True

    def test_needs_reminder_false_not_scheduled(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            scheduled_deletion_at=None,
            reminder_sent_at=None,
        )
        assert req.needs_reminder is False

    def test_needs_reminder_false_no_deletion_date(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
            scheduled_deletion_at=None,
            reminder_sent_at=None,
        )
        assert req.needs_reminder is False

    def test_needs_reminder_false_already_sent(self):
        deletion_at = datetime.now(UTC) + timedelta(hours=12)
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
            scheduled_deletion_at=deletion_at,
            reminder_sent_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert req.needs_reminder is False

    def test_needs_reminder_false_too_early(self):
        deletion_at = datetime.now(UTC) + timedelta(days=5)
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
            scheduled_deletion_at=deletion_at,
            reminder_sent_at=None,
        )
        assert req.needs_reminder is False


class TestWorkspaceDeletionRequestMutations:
    """Test confirm, schedule, mark_reminder_sent, execute_scheduled,
    cancel, mark_expired."""

    def test_confirm(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            confirmed_at=None,
        )
        req.confirm()
        assert req.status == DeletionRequestStatus.CONFIRMED
        assert req.confirmed_at is not None

    def test_schedule(self):
        deletion_date = datetime.now(UTC) + timedelta(days=30)
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            confirmed_at=None,
            scheduled_deletion_at=None,
            subscription_cancelled=False,
            cancel_token=None,
        )
        req.schedule(deletion_date, subscription_cancelled=True)
        assert req.status == DeletionRequestStatus.SCHEDULED
        assert req.confirmed_at is not None
        assert req.scheduled_deletion_at == deletion_date
        assert req.subscription_cancelled is True
        assert req.cancel_token is not None

    def test_schedule_default_subscription_cancelled(self):
        deletion_date = datetime.now(UTC) + timedelta(days=30)
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
            confirmed_at=None,
            scheduled_deletion_at=None,
            subscription_cancelled=False,
            cancel_token=None,
        )
        req.schedule(deletion_date)
        assert req.subscription_cancelled is True

    def test_mark_reminder_sent(self):
        req = _make(
            WorkspaceDeletionRequest,
            reminder_sent_at=None,
        )
        req.mark_reminder_sent()
        assert req.reminder_sent_at is not None

    def test_execute_scheduled(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
        )
        req.execute_scheduled()
        assert req.status == DeletionRequestStatus.CONFIRMED

    def test_cancel(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.SCHEDULED,
        )
        req.cancel()
        assert req.status == DeletionRequestStatus.CANCELLED

    def test_mark_expired(self):
        req = _make(
            WorkspaceDeletionRequest,
            status=DeletionRequestStatus.PENDING,
        )
        req.mark_expired()
        assert req.status == DeletionRequestStatus.EXPIRED
