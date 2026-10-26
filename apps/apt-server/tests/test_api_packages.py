# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Package API: upload, listing, update, delete, ACL and reindex."""

import uuid

import pytest
from apt_server.auth.dependencies import AuthContext
from apt_server.auth.models import User
from apt_server.db.models import IndexCache
from apt_server.services.caller import caller_from_auth
from debfactory import build_deb
from sqlalchemy import select

WRITER = ["apt:write"]
READER = ["apt:read"]
ADMIN = ["apt:admin"]


@pytest.fixture(autouse=True)
def _repository(repo_root, oidc_settings):
    return repo_root


async def upload(http, raw=None, suite="stable", component="main", visibility="private"):
    return await http.post(
        "/api/packages",
        files={"deb": ("demo.deb", raw or build_deb(), "application/vnd.debian.binary-package")},
        data={"suite": suite, "component": component, "visibility": visibility},
    )


def test_caller_from_auth_maps_identity() -> None:
    user = User(id="u1", scopes=["apt:read"], email="a@example.com")

    caller = caller_from_auth(AuthContext(user))

    assert caller.sub == "u1"
    assert caller.scopes == frozenset({"apt:read"})
    assert caller.display_name == "a@example.com"
    assert caller.groups == frozenset()


def test_caller_from_auth_falls_back_to_name_then_id() -> None:
    assert caller_from_auth(AuthContext(User(id="u1", name="Alice"))).display_name == "Alice"
    assert caller_from_auth(AuthContext(User(id="u1"))).display_name == "u1"


async def test_api_requires_authentication(http) -> None:
    assert (await http.get("/api/packages")).status_code == 401


async def test_upload_creates_a_package(http, login, repo_root) -> None:
    login("alice", WRITER)

    response = await upload(http, visibility="public")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "demo" and body["owner_id"] == "alice"
    assert body["visibility"] == "public"
    assert (repo_root / body["filename"]).is_file()


async def test_upload_requires_a_write_scope(http, login) -> None:
    login("alice", READER)

    response = await upload(http)

    assert response.status_code == 403
    assert "apt:write:main" in response.json()["detail"]


async def test_component_scoped_write_scope_is_limited(http, login) -> None:
    login("ci", ["apt:write:private"])

    assert (await upload(http, component="main")).status_code == 403
    assert (await upload(http, component="private")).status_code == 201


async def test_upload_rejects_invalid_archives_and_unknown_targets(http, login) -> None:
    login("alice", WRITER)

    assert (await upload(http, raw=b"garbage")).status_code == 400
    assert (await upload(http, component="rogue")).status_code == 400
    assert (await upload(http, suite="rogue")).status_code == 400


async def test_duplicate_upload_is_a_conflict(http, login) -> None:
    login("alice", WRITER)
    await upload(http)

    response = await upload(http)

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_list_only_returns_visible_packages(http, login) -> None:
    login("alice", WRITER)
    await upload(http, build_deb("mine"), visibility="private")
    await upload(http, build_deb("open"), visibility="public")
    login("bob", READER)

    names = [p["name"] for p in (await http.get("/api/packages")).json()]

    assert names == ["open"]


async def test_list_supports_filters(http, login) -> None:
    login("alice", ADMIN)
    await upload(http, build_deb("one"))
    await upload(http, build_deb("two"), component="private")

    by_component = (await http.get("/api/packages", params={"component": "private"})).json()
    by_name = (await http.get("/api/packages", params={"name": "one"})).json()
    by_suite = (await http.get("/api/packages", params={"suite": "nope"})).json()

    assert [p["name"] for p in by_component] == ["two"]
    assert [p["name"] for p in by_name] == ["one"]
    assert by_suite == []


async def test_get_hides_packages_the_caller_cannot_read(http, login) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]

    assert (await http.get(f"/api/packages/{package_id}")).status_code == 200
    login("bob", READER)
    assert (await http.get(f"/api/packages/{package_id}")).status_code == 404


async def test_unknown_package_is_not_found(http, login) -> None:
    login("alice", ADMIN)

    assert (await http.get(f"/api/packages/{uuid.uuid4()}")).status_code == 404


async def test_owner_updates_visibility_and_description(http, login, db) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]

    response = await http.patch(
        f"/api/packages/{package_id}", json={"visibility": "public", "description": "new text"}
    )

    assert response.status_code == 200
    assert response.json()["visibility"] == "public"
    assert response.json()["description"] == "new text"


async def test_update_invalidates_the_index_cache(http, login, db) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]
    db.add(IndexCache(cache_key="k", body=b"old", sha256="0" * 64))
    await db.commit()

    await http.patch(f"/api/packages/{package_id}", json={"visibility": "public"})

    assert (await db.execute(select(IndexCache))).scalars().all() == []


async def test_non_owner_cannot_update_or_delete(http, login) -> None:
    login("alice", WRITER)
    package_id = (await upload(http, visibility="public")).json()["id"]
    login("bob", WRITER)

    assert (await http.patch(f"/api/packages/{package_id}", json={})).status_code == 403
    assert (await http.delete(f"/api/packages/{package_id}")).status_code == 403


async def test_delete_removes_the_row_and_the_file(http, login, repo_root) -> None:
    login("alice", WRITER)
    created = (await upload(http)).json()

    response = await http.delete(f"/api/packages/{created['id']}")

    assert response.status_code == 204
    assert not (repo_root / created["filename"]).exists()
    assert (await http.get(f"/api/packages/{created['id']}")).status_code == 404


async def test_removed_component_makes_the_package_gone(http, login, monkeypatch) -> None:
    from apt_server.config import settings

    login("alice", ADMIN)
    package_id = (await upload(http, component="private")).json()["id"]
    monkeypatch.setattr(settings, "apt_components", "main")

    assert (await http.get(f"/api/packages/{package_id}")).status_code == 410


async def test_owner_manages_acl_entries(http, login) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]

    created = await http.post(
        f"/api/packages/{package_id}/acl", json={"grantee_user_id": "bob", "role": "write"}
    )
    listed = await http.get(f"/api/packages/{package_id}/acl")

    assert created.status_code == 201
    assert created.json()["granted_by"] == "alice"
    assert [e["grantee_user_id"] for e in listed.json()] == ["bob"]

    login("bob", READER)
    assert (await http.get(f"/api/packages/{package_id}")).status_code == 200

    login("alice", WRITER)
    deleted = await http.delete(f"/api/packages/{package_id}/acl/{created.json()['id']}")
    assert deleted.status_code == 204
    assert (await http.get(f"/api/packages/{package_id}/acl")).json() == []


async def test_group_grants_are_listed(http, login) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]

    created = await http.post(
        f"/api/packages/{package_id}/acl", json={"grantee_group": "team:ops", "role": "read"}
    )

    assert created.status_code == 201
    assert created.json()["grantee_group"] == "team:ops"
    assert created.json()["grantee_user_id"] is None


@pytest.mark.parametrize(
    "payload",
    [{}, {"grantee_user_id": "bob", "grantee_group": "team"}],
    ids=["none", "both"],
)
async def test_acl_needs_exactly_one_grantee(http, login, payload) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]

    response = await http.post(f"/api/packages/{package_id}/acl", json=payload)

    assert response.status_code == 400


async def test_duplicate_acl_entry_is_a_conflict(http, login) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]
    payload = {"grantee_user_id": "bob"}
    await http.post(f"/api/packages/{package_id}/acl", json=payload)

    assert (await http.post(f"/api/packages/{package_id}/acl", json=payload)).status_code == 409


async def test_acl_is_restricted_to_owner_and_admin(http, login) -> None:
    login("alice", WRITER)
    package_id = (await upload(http, visibility="public")).json()["id"]
    login("bob", WRITER)

    assert (await http.get(f"/api/packages/{package_id}/acl")).status_code == 403
    post = await http.post(f"/api/packages/{package_id}/acl", json={"grantee_user_id": "bob"})
    assert post.status_code == 403
    assert (await http.delete(f"/api/packages/{package_id}/acl/{uuid.uuid4()}")).status_code == 403
    login("root", ADMIN)
    assert (await http.get(f"/api/packages/{package_id}/acl")).status_code == 200


async def test_deleting_an_unknown_acl_entry_is_not_found(http, login) -> None:
    login("alice", WRITER)
    package_id = (await upload(http)).json()["id"]

    response = await http.delete(f"/api/packages/{package_id}/acl/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_reindex_requires_admin(http, login) -> None:
    login("alice", WRITER)

    response = await http.post("/api/reindex")

    assert response.status_code == 403


async def test_reindex_clears_the_cache(http, login, db) -> None:
    db.add(IndexCache(cache_key="k", body=b"old", sha256="0" * 64))
    await db.commit()
    login("root", ADMIN)

    response = await http.post("/api/reindex")

    assert response.status_code == 204
    db.expire_all()
    assert (await db.execute(select(IndexCache))).scalars().all() == []
