# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.tenant — TenantService flows not covered by the route tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.tenant import TenantService


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def service(repo):
    return TenantService(repository=repo)


@pytest.fixture
def db():
    return AsyncMock()


def _tenant(slug="acme"):
    tenant = MagicMock()
    tenant.id = uuid.uuid4()
    tenant.slug = slug
    return tenant


class TestEagerLoadedReads:
    @pytest.mark.asyncio
    async def test_get_by_id_with_branding(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_id_with_branding.return_value = tenant

        assert await service.get_by_id_with_branding(db, tenant.id) is tenant
        repo.find_by_id_with_branding.assert_awaited_once_with(db, tenant.id)

    @pytest.mark.asyncio
    async def test_get_by_id_with_templates(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_id_with_templates.return_value = tenant

        assert await service.get_by_id_with_templates(db, tenant.id) is tenant
        repo.find_by_id_with_templates.assert_awaited_once_with(db, tenant.id)

    @pytest.mark.asyncio
    async def test_get_by_slug(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_slug.return_value = tenant

        assert await service.get_by_slug(db, "acme") is tenant
        repo.find_by_slug.assert_awaited_once_with(db, "acme")

    @pytest.mark.asyncio
    async def test_get_settings(self, db, repo, service):
        repo.find_settings_by_id.return_value = {"mfa": True}
        tenant_id = uuid.uuid4()

        assert await service.get_settings(db, tenant_id) == {"mfa": True}
        repo.find_settings_by_id.assert_awaited_once_with(db, tenant_id)

    @pytest.mark.asyncio
    async def test_list_active_dropdown(self, db, repo, service):
        rows = [(uuid.uuid4(), "Acme", "acme")]
        repo.list_active_dropdown.return_value = rows

        assert await service.list_active_dropdown(db) == rows
        repo.list_active_dropdown.assert_awaited_once_with(db)


class TestResolveWithBranding:
    @pytest.mark.asyncio
    async def test_uuid_resolves_by_id(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_id_with_branding.return_value = tenant

        assert await service.resolve_with_branding(db, str(tenant.id)) is tenant
        repo.find_by_slug_with_branding.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_uuid_resolves_by_slug(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_slug_with_branding.return_value = tenant

        assert await service.resolve_with_branding(db, "acme") is tenant
        repo.find_by_id_with_branding.assert_not_awaited()


class TestResolveWithTemplates:
    @pytest.mark.asyncio
    async def test_uuid_resolves_by_id(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_id_with_templates.return_value = tenant

        assert await service.resolve_with_templates(db, str(tenant.id)) is tenant
        repo.find_by_slug_with_templates.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_uuid_resolves_by_slug(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_slug_with_templates.return_value = tenant

        assert await service.resolve_with_templates(db, "acme") is tenant
        repo.find_by_id_with_templates.assert_not_awaited()


class TestCreateTenant:
    @pytest.mark.asyncio
    async def test_duplicate_slug_rejected(self, db, repo, service):
        repo.find_by_slug.return_value = _tenant()

        with pytest.raises(ValueError, match="Slug already exists"):
            await service.create_tenant(db, slug="acme", display_name="Acme")

    @pytest.mark.asyncio
    async def test_seeds_default_roles(self, db, repo, service):
        repo.find_by_slug.return_value = None

        with patch(
            "auth.services.tenant.tenant_role_service.create_default_roles", AsyncMock()
        ) as create_roles:
            tenant = await service.create_tenant(db, slug="acme", display_name="Acme")

        assert tenant.slug == "acme"
        assert tenant.settings == {}
        create_roles.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_role_seeding_can_be_disabled(self, db, repo, service):
        repo.find_by_slug.return_value = None

        with patch(
            "auth.services.tenant.tenant_role_service.create_default_roles", AsyncMock()
        ) as create_roles:
            tenant = await service.create_tenant(
                db,
                slug="acme",
                display_name="Acme",
                settings={"mfa": True},
                create_default_roles=False,
            )

        assert tenant.settings == {"mfa": True}
        create_roles.assert_not_awaited()


class TestUpdateTenant:
    @pytest.mark.asyncio
    async def test_sparse_update_leaves_other_fields_alone(self, db, repo, service):
        tenant = _tenant()
        tenant.display_name = "Old"
        tenant.custom_domain = "old.example.com"
        tenant.is_active = True
        tenant.settings = {"a": 1}

        await service.update_tenant(db, tenant, display_name="New")

        assert tenant.display_name == "New"
        assert tenant.custom_domain == "old.example.com"
        assert tenant.is_active is True
        assert tenant.settings == {"a": 1}
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_blank_custom_domain_is_normalised_to_none(self, db, repo, service):
        tenant = _tenant()

        await service.update_tenant(db, tenant, custom_domain="")

        assert tenant.custom_domain is None

    @pytest.mark.asyncio
    async def test_all_fields_updated(self, db, repo, service):
        tenant = _tenant()

        await service.update_tenant(
            db,
            tenant,
            display_name="New",
            custom_domain="new.example.com",
            is_active=False,
            settings={"b": 2},
        )

        assert tenant.display_name == "New"
        assert tenant.custom_domain == "new.example.com"
        assert tenant.is_active is False
        assert tenant.settings == {"b": 2}


class TestListUserMembershipsWithCustomRole:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        memberships = [MagicMock()]
        repo.list_user_memberships_with_custom_role.return_value = memberships
        user_id = uuid.uuid4()

        assert await service.list_user_memberships_with_custom_role(db, user_id) == memberships
        repo.list_user_memberships_with_custom_role.assert_awaited_once_with(db, user_id)


class TestCreateOrganisationWithOwner:
    @pytest.mark.asyncio
    async def test_duplicate_slug_rejected(self, db, repo, service):
        repo.find_by_slug.return_value = _tenant()

        with pytest.raises(ValueError, match="Slug already exists"):
            await service.create_organisation_with_owner(
                db, slug="acme", display_name="Acme", owner_user_id=uuid.uuid4()
            )

    @pytest.mark.asyncio
    async def test_owner_role_is_assigned(self, db, repo, service):
        repo.find_by_slug.return_value = None
        owner_role = MagicMock()
        owner_role.name = "owner"
        owner_role.id = uuid.uuid4()
        other_role = MagicMock()
        other_role.name = "member"
        owner_user_id = uuid.uuid4()

        with patch(
            "auth.services.tenant.tenant_role_service.create_default_roles",
            AsyncMock(return_value=[other_role, owner_role]),
        ):
            tenant, member = await service.create_organisation_with_owner(
                db, slug="acme", display_name="Acme", owner_user_id=owner_user_id
            )

        assert tenant.slug == "acme"
        assert member.user_id == owner_user_id
        assert member.role_id == owner_role.id
        db.refresh.assert_awaited_once_with(member, ["custom_role"])

    @pytest.mark.asyncio
    async def test_missing_owner_role_leaves_role_id_null(self, db, repo, service):
        repo.find_by_slug.return_value = None
        other_role = MagicMock()
        other_role.name = "member"

        with patch(
            "auth.services.tenant.tenant_role_service.create_default_roles",
            AsyncMock(return_value=[other_role]),
        ):
            _tenant_row, member = await service.create_organisation_with_owner(
                db, slug="acme", display_name="Acme", owner_user_id=uuid.uuid4()
            )

        assert member.role_id is None


class TestBrandingHelpers:
    @pytest.mark.asyncio
    async def test_get_branding(self, db, repo, service):
        branding = MagicMock()
        repo.find_branding.return_value = branding
        tenant_id = uuid.uuid4()

        assert await service.get_branding(db, tenant_id) is branding
        repo.find_branding.assert_awaited_once_with(db, tenant_id)

    @pytest.mark.asyncio
    async def test_delete_branding(self, db, repo, service):
        branding = MagicMock()

        await service.delete_branding(db, branding)

        repo.delete.assert_awaited_once_with(db, branding)

    @pytest.mark.asyncio
    async def test_add_branding(self, db, repo, service):
        branding = MagicMock()

        assert await service.add_branding(db, branding) is branding
        repo.add_branding.assert_awaited_once_with(db, branding)


class TestCustomRoleHelpers:
    @pytest.mark.asyncio
    async def test_get_custom_role_scoped(self, db, repo, service):
        role = MagicMock()
        repo.find_custom_role_scoped.return_value = role
        role_id, tenant_id = uuid.uuid4(), uuid.uuid4()

        assert await service.get_custom_role_scoped(db, role_id, tenant_id) is role
        repo.find_custom_role_scoped.assert_awaited_once_with(db, role_id, tenant_id)

    @pytest.mark.asyncio
    async def test_count_members_for_role(self, db, repo, service):
        repo.count_members_for_role.return_value = 4
        role_id = uuid.uuid4()

        assert await service.count_members_for_role(db, role_id) == 4
        repo.count_members_for_role.assert_awaited_once_with(db, role_id)

    @pytest.mark.asyncio
    async def test_delete_custom_role(self, db, repo, service):
        role = MagicMock()

        await service.delete_custom_role(db, role)

        repo.delete.assert_awaited_once_with(db, role)


class TestMemberEmailHelpers:
    @pytest.mark.asyncio
    async def test_get_member_primary_email(self, db, repo, service):
        repo.find_primary_email_for_user.return_value = "a@example.com"
        user_id = uuid.uuid4()

        assert await service.get_member_primary_email(db, user_id) == "a@example.com"
        repo.find_primary_email_for_user.assert_awaited_once_with(db, user_id)


class TestScopedLookups:
    @pytest.mark.asyncio
    async def test_get_idp_scoped_with_federated(self, db, repo, service):
        idp = MagicMock()
        repo.find_idp_scoped_with_federated.return_value = idp
        idp_id, tenant_id = uuid.uuid4(), uuid.uuid4()

        assert await service.get_idp_scoped_with_federated(db, idp_id, tenant_id) is idp
        repo.find_idp_scoped_with_federated.assert_awaited_once_with(db, idp_id, tenant_id)

    @pytest.mark.asyncio
    async def test_get_member_in_tenant_defaults_to_eager_role(self, db, repo, service):
        member = MagicMock()
        repo.find_member_in_tenant.return_value = member
        member_id, tenant_id = uuid.uuid4(), uuid.uuid4()

        assert await service.get_member_in_tenant(db, member_id, tenant_id) is member
        repo.find_member_in_tenant.assert_awaited_once_with(
            db, member_id, tenant_id, eager_role=True
        )

    @pytest.mark.asyncio
    async def test_get_member_in_tenant_without_eager_role(self, db, repo, service):
        repo.find_member_in_tenant.return_value = None

        await service.get_member_in_tenant(db, uuid.uuid4(), uuid.uuid4(), eager_role=False)

        assert repo.find_member_in_tenant.await_args.kwargs["eager_role"] is False


class TestGetByCustomDomain:
    @pytest.mark.asyncio
    async def test_delegates_to_the_repository(self, db, repo, service):
        tenant = _tenant()
        repo.find_by_custom_domain.return_value = tenant

        assert await service.get_by_custom_domain(db, "auth.acme.example") is tenant
        repo.find_by_custom_domain.assert_awaited_once_with(db, "auth.acme.example")
