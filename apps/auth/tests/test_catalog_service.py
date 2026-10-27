# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.catalog — the declarative catalog of scopes, roles and grants."""

import json
from unittest.mock import AsyncMock

import pytest
from auth.db.models.rbac import ADMIN_SCOPES, DEFAULT_ROLES
from auth.services.catalog import (
    Catalog,
    CatalogError,
    SyncReport,
    load_catalog,
    parse_catalog,
    sync_catalog,
)

from tests.fakes_catalog import FakeCatalogRepository


def catalog(**document):
    return parse_catalog({"version": 1, **document})


class TestParsing:
    def test_minimal_document(self):
        parsed = catalog()
        assert parsed.scopes == [] and parsed.roles == [] and parsed.clients == []

    def test_scope_defaults(self):
        scope = catalog(scopes=[{"name": "notes:read"}]).scopes[0]
        assert scope.category == "api"
        assert scope.is_system is True and scope.is_active is True
        assert scope.resolved_resource() == "notes"
        assert scope.resolved_action() == "read"

    @pytest.mark.parametrize(
        ("name", "resource", "action"),
        [
            ("*", "*", "*"),
            ("notes:*", "notes", "*"),
            ("billing:checkout:write", "billing", "write"),
            ("custom-domain:read", "custom-domain", "read"),
            ("search", "search", "*"),
        ],
    )
    def test_resource_and_action_come_from_the_name(self, name, resource, action):
        scope = catalog(scopes=[{"name": name}]).scopes[0]
        assert (scope.resolved_resource(), scope.resolved_action()) == (resource, action)

    def test_explicit_resource_and_action_win(self):
        scope = catalog(scopes=[{"name": "a:b", "resource": "r", "action": "x"}]).scopes[0]
        assert (scope.resolved_resource(), scope.resolved_action()) == ("r", "x")

    @pytest.mark.parametrize("name", ["", "has space", "a::b", ":a", "a:", "x" * 101])
    def test_bad_scope_names_are_rejected(self, name):
        with pytest.raises(CatalogError):
            catalog(scopes=[{"name": name}])

    def test_unknown_keys_are_rejected(self):
        with pytest.raises(CatalogError, match="invalid catalog"):
            catalog(scopes=[{"name": "a:b", "colour": "red"}])
        with pytest.raises(CatalogError, match="invalid catalog"):
            catalog(permissions=[])

    def test_only_version_one_is_known(self):
        with pytest.raises(CatalogError):
            parse_catalog({"version": 2})

    @pytest.mark.parametrize(
        ("key", "entries", "word"),
        [
            ("scopes", [{"name": "a:b"}, {"name": "a:b"}], "scope"),
            ("roles", [{"name": "r"}, {"name": "r"}], "role"),
            ("clients", [{"client_id": "c"}, {"client_id": "c"}], "client"),
        ],
    )
    def test_duplicates_are_rejected(self, key, entries, word):
        with pytest.raises(CatalogError, match=f"duplicated {word}"):
            catalog(**{key: entries})

    def test_builtin_catalog_is_the_scopes_and_roles_of_the_code(self):
        builtin = Catalog.builtin()
        assert {s.name for s in builtin.scopes} == set(ADMIN_SCOPES)
        assert {s.category for s in builtin.scopes} == {"admin"}
        assert {r.name for r in builtin.roles} == set(DEFAULT_ROLES)
        assert next(r for r in builtin.roles if r.name == "super_admin").scopes == ["*"]


class TestLoading:
    def test_load_a_file(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps({"scopes": [{"name": "notes:read"}]}))
        assert load_catalog(path).scopes[0].name == "notes:read"

    def test_missing_file(self, tmp_path):
        with pytest.raises(CatalogError, match="cannot read"):
            load_catalog(tmp_path / "absent.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text("{not json")
        with pytest.raises(CatalogError, match="not valid JSON"):
            load_catalog(path)


class TestSync:
    async def sync(self, repo, **document):
        return await sync_catalog(AsyncMock(), catalog(**document), repo)

    async def test_creates_the_missing_scopes_and_roles(self):
        repo = FakeCatalogRepository()
        report = await self.sync(
            repo,
            scopes=[
                {"name": "notes:read", "description": "Read notes"},
                {"name": "notes:write", "category": "app", "is_system": False},
            ],
            roles=[{"name": "notes_editor", "scopes": ["notes:read", "notes:write"]}],
        )
        assert report.created == [
            "scope notes:read",
            "scope notes:write",
            "role notes_editor with 2 scope(s)",
        ]
        assert report.changed
        read = repo.scopes["notes:read"]
        assert (read.resource, read.action, read.category) == ("notes", "read", "api")
        assert repo.scopes["notes:write"].is_system is False
        assert {rs.scope.name for rs in repo.roles["notes_editor"].role_scopes} == {
            "notes:read",
            "notes:write",
        }

    async def test_second_run_changes_nothing(self):
        repo = FakeCatalogRepository()
        document = {
            "scopes": [{"name": "notes:read", "description": "Read"}],
            "roles": [{"name": "viewer", "description": "V", "scopes": ["notes:read"]}],
        }
        await self.sync(repo, **document)
        report = await self.sync(repo, **document)
        assert not report.changed
        assert report.lines() == []

    async def test_descriptions_are_updated_but_not_erased(self):
        repo = FakeCatalogRepository()
        repo.add_scope("notes:read", "old")
        repo.add_role("viewer", "old", ["notes:read"])
        report = await self.sync(
            repo,
            scopes=[{"name": "notes:read", "description": "new"}],
            roles=[{"name": "viewer", "description": "new", "scopes": []}],
        )
        assert report.updated == ["scope notes:read (description)", "role viewer (description)"]
        assert repo.scopes["notes:read"].description == "new"
        report = await self.sync(repo, scopes=[{"name": "notes:read"}], roles=[{"name": "viewer"}])
        assert not report.changed
        assert repo.scopes["notes:read"].description == "new"

    async def test_scopes_are_added_to_an_existing_role_and_never_removed(self):
        repo = FakeCatalogRepository()
        repo.add_scope("a:read")
        repo.add_scope("b:read")
        repo.add_role("viewer", "V", ["a:read"])
        report = await self.sync(repo, roles=[{"name": "viewer", "scopes": ["b:read"]}])
        assert report.updated == ["role viewer (+b:read)"]
        assert {rs.scope.name for rs in repo.roles["viewer"].role_scopes} == {"a:read", "b:read"}

    async def test_a_role_may_use_a_scope_the_database_already_has(self):
        repo = FakeCatalogRepository()
        repo.add_scope("*")
        report = await self.sync(repo, roles=[{"name": "root", "scopes": ["*"]}])
        assert report.created == ["role root with 1 scope(s)"]

    async def test_unknown_scope_of_a_role_is_an_error_and_writes_nothing(self):
        repo = FakeCatalogRepository()
        with pytest.raises(CatalogError, match="unknown scopes: ghost:read"):
            await self.sync(
                repo,
                scopes=[{"name": "a:read"}],
                roles=[{"name": "r", "scopes": ["a:read", "ghost:read"]}],
            )
        assert repo.scopes == {} and repo.roles == {}

    async def test_client_allowances_are_added(self):
        repo = FakeCatalogRepository()
        client = repo.add_client("kb", ["openid"], ["authorization_code"])
        report = await self.sync(
            repo,
            clients=[
                {
                    "client_id": "kb",
                    "allowed_scopes": ["openid", "billing:checkout:write"],
                    "allowed_grant_types": ["client_credentials"],
                }
            ],
        )
        assert client.allowed_scopes == ["openid", "billing:checkout:write"]
        assert client.allowed_grant_types == ["authorization_code", "client_credentials"]
        assert report.updated == [
            "client kb (+billing:checkout:write, +client_credentials)",
        ]
        again = await self.sync(
            repo, clients=[{"client_id": "kb", "allowed_scopes": ["billing:checkout:write"]}]
        )
        assert not again.changed

    async def test_unknown_client_is_skipped_not_created(self):
        repo = FakeCatalogRepository()
        report = await self.sync(repo, clients=[{"client_id": "ghost", "allowed_scopes": ["x"]}])
        assert report.skipped == ["client ghost (not found)"]
        assert not report.changed
        assert repo.clients == {}

    async def test_builtin_catalog_creates_the_admin_scopes_and_roles(self):
        repo = FakeCatalogRepository()
        report = await sync_catalog(AsyncMock(), Catalog.builtin(), repo)
        assert len(repo.scopes) == len(ADMIN_SCOPES)
        assert set(repo.roles) == set(DEFAULT_ROLES)
        operator = {rs.scope.name for rs in repo.roles["operator"].role_scopes}
        assert operator == set(DEFAULT_ROLES["operator"]["scopes"])
        assert report.changed


class TestReport:
    def test_serialisation(self):
        report = SyncReport(created=["scope a:b"], updated=["role r (description)"], skipped=["x"])
        assert report.to_dict() == {
            "changed": True,
            "created": ["scope a:b"],
            "updated": ["role r (description)"],
            "skipped": ["x"],
        }
        assert report.lines() == [
            "created scope a:b",
            "updated role r (description)",
            "skipped x",
        ]
        assert report.lines(dry_run=True) == [
            "would create scope a:b",
            "would update role r (description)",
            "would skip x",
        ]

    def test_skipped_alone_is_not_a_change(self):
        assert SyncReport(skipped=["x"]).changed is False

    def test_extend(self):
        first = SyncReport(created=["a"])
        first.extend(SyncReport(updated=["b"], skipped=["c"]))
        assert (first.created, first.updated, first.skipped) == (["a"], ["b"], ["c"])
