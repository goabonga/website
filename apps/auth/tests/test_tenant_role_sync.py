# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for TenantRoleService.sync_default_roles — the system roles of existing organisations."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.models.tenant import DEFAULT_TENANT_ROLES, TenantCustomRole
from auth.services.tenant_role import TenantRoleService


def _role(tenant_id, name, scopes=None, *, is_system=True, is_default=False):
    config = DEFAULT_TENANT_ROLES.get(name, {})
    return TenantCustomRole(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        display_name=config.get("display_name", name.title()),
        description=config.get("description"),
        scopes=list(config["scopes"] if scopes is None else scopes),
        is_system=is_system,
        is_default=is_default,
        display_order=config.get("display_order", 9),
    )


def _service(tenants, roles, with_default=()):
    repo = MagicMock()
    repo.list_tenant_refs = AsyncMock(return_value=tenants)
    repo.list_roles_named = AsyncMock(return_value=roles)
    repo.list_tenant_ids_with_default_role = AsyncMock(return_value=set(with_default))
    repo.stage = AsyncMock()
    repo.flush = AsyncMock()
    return TenantRoleService(repository=repo), repo


@pytest.fixture
def db():
    return AsyncMock()


def _full(tenant_id):
    return [_role(tenant_id, name, is_default=(name == "member")) for name in DEFAULT_TENANT_ROLES]


def _legacy_admin(tenant_id):
    """The admin role as it was stored before the defaults held domain:read."""
    scopes = [s for s in DEFAULT_TENANT_ROLES["admin"]["scopes"] if s != "domain:read"]
    return _role(tenant_id, "admin", scopes)


def test_the_admin_default_reads_the_domain_and_does_not_write_it():
    scopes = DEFAULT_TENANT_ROLES["admin"]["scopes"]
    assert "domain:read" in scopes
    assert not {"domain:write", "domain:*", "*"} & set(scopes)


class TestAddsTheMissingScopes:
    async def test_an_admin_role_created_before_domain_read_receives_it(self, db):
        tenant = uuid.uuid4()
        admin = _legacy_admin(tenant)
        others = [r for r in _full(tenant) if r.name != "admin"]
        service, repo = _service([(tenant, "acme")], [admin, *others])

        report = await service.sync_default_roles(db)

        assert admin.scopes[-1] == "domain:read"
        assert admin.scopes[:-1] == [
            s for s in DEFAULT_TENANT_ROLES["admin"]["scopes"] if s != "domain:read"
        ]
        assert report.changed is True
        assert report.updated == ["organisation acme role admin (+domain:read)"]
        assert report.created == [] and report.skipped == []
        assert report.tenants == {"acme": {"created": [], "added": {"admin": ["domain:read"]}}}
        repo.stage.assert_not_awaited()
        repo.flush.assert_awaited_once_with(db)

    async def test_a_second_run_changes_nothing(self, db):
        tenant = uuid.uuid4()
        roles = [_legacy_admin(tenant), *[r for r in _full(tenant) if r.name != "admin"]]
        service, _repo = _service([(tenant, "acme")], roles)

        await service.sync_default_roles(db)
        again = await service.sync_default_roles(db)

        assert again.changed is False
        assert again.to_dict() == {
            "changed": False,
            "created": [],
            "updated": [],
            "skipped": [],
            "tenants": {},
        }

    async def test_what_an_organisation_added_is_kept(self, db):
        tenant = uuid.uuid4()
        admin = _role(tenant, "admin", ["members:*", "billing:read", "custom:thing"])
        rest = [r for r in _full(tenant) if r.name != "admin"]
        service, _repo = _service([(tenant, "acme")], [admin, *rest])

        await service.sync_default_roles(db)

        assert admin.scopes[:3] == ["members:*", "billing:read", "custom:thing"]
        assert set(DEFAULT_TENANT_ROLES["admin"]["scopes"]) <= set(admin.scopes)

    async def test_a_scope_granted_by_a_wildcard_is_not_added(self, db):
        tenant = uuid.uuid4()
        admin = _role(tenant, "admin", ["members:*", "domain:*", "idp:*"])
        member = _role(tenant, "member", ["*"])
        service, _repo = _service([(tenant, "acme")], [admin, member, _role(tenant, "owner")])

        await service.sync_default_roles(db)

        assert "domain:read" not in admin.scopes
        assert member.scopes == ["*"]
        assert "members:*" in admin.scopes and admin.scopes.count("members:*") == 1

    async def test_the_owner_wildcard_needs_nothing(self, db):
        tenant = uuid.uuid4()
        owner = _role(tenant, "owner", ["*"])
        service, _repo = _service(
            [(tenant, "acme")], [owner, *[r for r in _full(tenant) if r.name != "owner"]]
        )

        report = await service.sync_default_roles(db)

        assert owner.scopes == ["*"]
        assert report.changed is False

    async def test_every_organisation_is_reported_on_its_own(self, db):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        roles = [
            _legacy_admin(a),
            *[r for r in _full(a) if r.name != "admin"],
            *_full(b),
            _legacy_admin(c),
            *[r for r in _full(c) if r.name != "admin"],
        ]
        service, _repo = _service([(a, "alpha"), (b, "beta"), (c, "gamma")], roles)

        report = await service.sync_default_roles(db)

        assert sorted(report.tenants) == ["alpha", "gamma"]
        assert report.updated == [
            "organisation alpha role admin (+domain:read)",
            "organisation gamma role admin (+domain:read)",
        ]


class TestCreatesMissingRoles:
    async def test_a_missing_system_role_is_created_like_a_new_organisation_gets_it(self, db):
        tenant = uuid.uuid4()
        owner, admin = _role(tenant, "owner"), _role(tenant, "admin")
        service, repo = _service([(tenant, "acme")], [owner, admin])

        report = await service.sync_default_roles(db)

        repo.stage.assert_awaited_once()
        created = repo.stage.await_args.args[1]
        config = DEFAULT_TENANT_ROLES["member"]
        assert (created.tenant_id, created.name, created.is_system) == (tenant, "member", True)
        assert created.scopes == config["scopes"] and created.scopes is not config["scopes"]
        assert created.display_name == config["display_name"]
        assert created.display_order == config["display_order"]
        assert created.is_default is True
        assert report.created == ["organisation acme role member with 1 scope(s)"]
        assert report.tenants["acme"] == {"created": ["member"], "added": {}}

    async def test_the_member_role_is_not_the_default_when_another_role_is(self, db):
        tenant = uuid.uuid4()
        roles = [_role(tenant, "owner"), _role(tenant, "admin")]
        service, repo = _service([(tenant, "acme")], roles, with_default=[tenant])

        await service.sync_default_roles(db)

        assert repo.stage.await_args.args[1].is_default is False

    async def test_an_organisation_without_any_role_gets_the_three(self, db):
        tenant = uuid.uuid4()
        service, repo = _service([(tenant, "bare")], [])

        report = await service.sync_default_roles(db)

        staged = [call.args[1] for call in repo.stage.await_args_list]
        assert [r.name for r in staged] == list(DEFAULT_TENANT_ROLES)
        assert [r.is_default for r in staged] == [False, False, True]
        assert report.tenants["bare"]["created"] == ["owner", "admin", "member"]


class TestLeavesTheRestAlone:
    async def test_a_custom_role_with_a_system_name_is_skipped(self, db):
        tenant = uuid.uuid4()
        custom = _role(tenant, "admin", ["something:else"], is_system=False)
        rest = [r for r in _full(tenant) if r.name != "admin"]
        service, repo = _service([(tenant, "acme")], [custom, *rest])

        report = await service.sync_default_roles(db)

        assert custom.scopes == ["something:else"]
        assert report.skipped == ["organisation acme role admin (not a system role, left as it is)"]
        assert report.changed is False
        repo.stage.assert_not_awaited()

    async def test_names_and_flags_of_the_existing_roles_are_not_touched(self, db):
        tenant = uuid.uuid4()
        admin = _legacy_admin(tenant)
        admin.display_name, admin.description, admin.display_order = "Boss", "Our boss", 7
        admin.is_default = True
        service, _repo = _service(
            [(tenant, "acme")], [admin, *[r for r in _full(tenant) if r.name != "admin"]]
        )

        await service.sync_default_roles(db)

        assert (admin.display_name, admin.description, admin.display_order) == (
            "Boss",
            "Our boss",
            7,
        )
        assert admin.is_default is True

    async def test_no_organisation_no_change(self, db):
        service, repo = _service([], [])

        report = await service.sync_default_roles(db)

        assert report.changed is False
        repo.stage.assert_not_awaited()

    async def test_the_default_constants_are_not_shared_with_the_stored_roles(self, db):
        tenant = uuid.uuid4()
        before = list(DEFAULT_TENANT_ROLES["admin"]["scopes"])
        admin = _legacy_admin(tenant)
        service, _repo = _service(
            [(tenant, "acme")], [admin, *[r for r in _full(tenant) if r.name != "admin"]]
        )

        await service.sync_default_roles(db)

        assert DEFAULT_TENANT_ROLES["admin"]["scopes"] == before
