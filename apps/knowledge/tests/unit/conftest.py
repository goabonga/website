# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit test fixtures using only unittest.mock. No real database."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from knowledge.models.enums import (
    OrganizationMemberRole,
    OwnerType,
    PlanType,
)


def _make_result(
    scalar_one_or_none=None,
    scalar=0,
    scalars_all=None,
    rowcount=0,
):
    """Create a mock SQLAlchemy Result object."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    result.rowcount = rowcount
    return result


@pytest.fixture
def mock_db():
    """Mock AsyncSession. Default execute returns None/0/[]."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_make_result())
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def make_result():
    """Factory fixture to create mock results for db.execute()."""
    return _make_result


@pytest.fixture
def user_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def other_user_id() -> UUID:
    return UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def org_id() -> UUID:
    return UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest.fixture
def collection_id() -> UUID:
    return UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture
def tenant_id() -> UUID:
    return UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest.fixture
def mock_collection(collection_id, user_id):
    """USER-owned collection."""
    coll = MagicMock()
    coll.id = collection_id
    coll.owner_type = OwnerType.USER
    coll.owner_id = user_id
    coll.organization_id = None
    coll.name = "Test Collection"
    coll.slug = "test-collection"
    coll.description = "A test collection"
    coll.embedding_model = "text-embedding-3-small"
    coll.dimension = 1536
    coll.metadata_schema = None
    coll.document_count = 0
    return coll


@pytest.fixture
def mock_org_collection(collection_id, org_id):
    """ORGANIZATION-owned collection."""
    coll = MagicMock()
    coll.id = collection_id
    coll.owner_type = OwnerType.ORGANIZATION
    coll.owner_id = org_id
    coll.organization_id = org_id
    coll.name = "Org Collection"
    coll.slug = "org-collection"
    return coll


@pytest.fixture
def mock_org_member_owner(user_id, org_id):
    member = MagicMock()
    member.organization_id = org_id
    member.user_id = user_id
    member.role = OrganizationMemberRole.OWNER
    member.is_admin = True
    member.is_owner = True
    return member


@pytest.fixture
def mock_org_member_admin(user_id, org_id):
    member = MagicMock()
    member.organization_id = org_id
    member.user_id = user_id
    member.role = OrganizationMemberRole.ADMIN
    member.is_admin = True
    member.is_owner = False
    return member


@pytest.fixture
def mock_org_member(user_id, org_id):
    member = MagicMock()
    member.organization_id = org_id
    member.user_id = user_id
    member.role = OrganizationMemberRole.MEMBER
    member.is_admin = False
    member.is_owner = False
    return member


@pytest.fixture
def mock_tenant(tenant_id):
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.name = "Test Org"
    tenant.slug = "test-org"
    tenant.plan = PlanType.ENTERPRISE
    tenant.is_active = True
    tenant.allow_member_create_collections = True
    return tenant


@pytest.fixture
def mock_free_tenant(tenant_id):
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.name = "Free Org"
    tenant.slug = "free-org"
    tenant.plan = PlanType.FREE
    tenant.is_active = True
    return tenant
