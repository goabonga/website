# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authenticated dashboard: own packages, upload, visibility and sharing."""

import re
import uuid

import pytest
from apt_server.config import settings
from apt_server.db.models import ACLRole, IndexCache, Package, PackageACL, PackageVisibility
from apt_server.routes.dashboard import PAGE_SIZE
from debfactory import build_deb
from sqlalchemy import select


def make_package(name, owner="alice", visibility=PackageVisibility.PRIVATE, **extra) -> Package:
    package = Package(
        name=name,
        version="1.0",
        architecture="amd64",
        suite="stable",
        component=extra.pop("component", "main"),
        owner_id=owner,
        visibility=visibility,
        filename=f"pool/main/{name[0]}/{name}/{name}_{uuid.uuid4().hex}.deb",
        size=10,
        md5="0" * 32,
        sha1="1" * 40,
        sha256="2" * 64,
        control={"Package": name},
    )
    package.acl.extend(extra.pop("acl", []))
    return package


@pytest.fixture(autouse=True)
def repository(repo_root, monkeypatch):
    monkeypatch.setattr(settings, "apt_suites", "stable,testing")
    return repo_root


@pytest.fixture
async def mine(db) -> Package:
    package = make_package("tool")
    db.add_all([package, make_package("theirs", owner="bob")])
    await db.commit()
    return package


async def test_dashboard_redirects_anonymous_visitors_to_login(http, login_caller) -> None:
    login_caller(None)

    for method, path in [("get", "/dashboard"), ("get", "/dashboard/upload")]:
        response = await getattr(http, method)(path)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


async def test_dashboard_lists_only_the_callers_packages(http, login_caller, mine) -> None:
    login_caller("alice", [])

    text = (await http.get("/dashboard")).text

    assert "tool" in text and "theirs" not in text


async def test_dashboard_filters_and_paginates(http, login_caller, db) -> None:
    db.add_all([make_package(f"pkg{i:03d}") for i in range(PAGE_SIZE + 3)])
    db.add(make_package("other", component="private"))
    await db.commit()
    login_caller("alice", [])

    first = (await http.get("/dashboard")).text
    second = (await http.get("/dashboard", params={"page": 2})).text
    by_component = (await http.get("/dashboard", params={"component": "private"})).text
    by_name = (await http.get("/dashboard", params={"q": "pkg001"})).text

    assert "pkg000" in first and "pkg025" not in first
    assert "pkg025" in second
    assert "other" in by_component and "pkg000" not in by_component
    assert "pkg001" in by_name and "pkg002" not in by_name


async def test_navigation_links_to_the_dashboard_for_signed_in_users(http, login_caller) -> None:
    login_caller("alice", [])

    text = (await http.get("/")).text

    assert 'href="/dashboard"' in text and 'href="/dashboard/upload"' in text


async def test_upload_form_shows_the_chunk_size(http, login_caller) -> None:
    login_caller("alice", [])

    response = await http.get("/dashboard/upload")

    assert response.status_code == 200
    assert str(settings.upload_chunk_size) in response.text


async def test_form_labels_are_bound_to_their_controls(http, login_caller, mine) -> None:
    login_caller("alice", [])

    for path in ("/dashboard/upload", f"/dashboard/{mine.id}/share"):
        page = (await http.get(path)).text
        targets = re.findall(r'<label for="([^"]+)"', page)
        assert len(targets) == len(re.findall(r"<label", page)), f"unbound label on {path}"
        assert all(f'id="{target}"' in page for target in targets), f"dangling label on {path}"


async def upload(http, raw=None, visibility="private", component="main"):
    return await http.post(
        "/dashboard/upload",
        files={"deb": ("demo.deb", raw or build_deb(), "application/octet-stream")},
        data={"suite": "stable", "component": component, "visibility": visibility},
    )


async def test_upload_stores_the_package_and_redirects(http, login_caller, db, repo_root) -> None:
    login_caller("alice", [])

    response = await upload(http, visibility="public")

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    package = (await db.execute(select(Package))).scalar_one()
    assert package.owner_id == "alice"
    assert package.visibility == PackageVisibility.PUBLIC
    assert (repo_root / package.filename).is_file()


async def test_upload_does_not_require_api_scopes(http, login_caller, db) -> None:
    login_caller("alice", [], is_session=True)

    assert (await upload(http)).status_code == 303


async def test_unknown_visibility_is_stored_as_private(http, login_caller, db) -> None:
    login_caller("alice", [])

    await upload(http, visibility="weird")

    assert (await db.execute(select(Package))).scalar_one().visibility == PackageVisibility.PRIVATE


async def test_invalid_upload_re_renders_the_form(http, login_caller) -> None:
    login_caller("alice", [])

    response = await upload(http, raw=b"garbage")

    assert response.status_code == 400
    assert "<form" in response.text


async def test_duplicate_upload_is_a_conflict(http, login_caller) -> None:
    login_caller("alice", [])
    await upload(http)

    response = await upload(http)

    assert response.status_code == 409
    assert "<form" in response.text


async def test_delete_removes_the_package_and_the_file(http, login_caller, db, repo_root) -> None:
    login_caller("alice", [])
    await upload(http)
    package = (await db.execute(select(Package))).scalar_one()
    package_id, filename = package.id, package.filename

    response = await http.post(f"/dashboard/{package_id}/delete")

    assert response.status_code == 303
    db.expire_all()
    assert (await db.execute(select(Package))).scalars().all() == []
    assert not (repo_root / filename).exists()


async def test_only_writers_can_delete(http, login_caller, mine) -> None:
    login_caller("mallory", [])

    assert (await http.post(f"/dashboard/{mine.id}/delete")).status_code == 403
    assert (await http.post(f"/dashboard/{uuid.uuid4()}/delete")).status_code == 404


async def test_visibility_change(http, login_caller, mine, db) -> None:
    package_id = mine.id
    login_caller("alice", [])
    db.add(IndexCache(cache_key="k", body=b"x", sha256="0" * 64))
    await db.commit()

    response = await http.post(f"/dashboard/{package_id}/visibility", data={"visibility": "public"})

    assert response.status_code == 303
    assert response.headers["location"] == f"/dashboard/{package_id}/share"
    db.expire_all()
    assert (await db.get(Package, package_id)).visibility == PackageVisibility.PUBLIC
    assert (await db.execute(select(IndexCache))).scalars().all() == []


async def test_invalid_visibility_is_ignored(http, login_caller, mine, db) -> None:
    package_id = mine.id
    login_caller("alice", [])

    await http.post(f"/dashboard/{package_id}/visibility", data={"visibility": "bogus"})

    db.expire_all()
    assert (await db.get(Package, package_id)).visibility == PackageVisibility.PRIVATE


async def test_share_page_lists_grants(http, login_caller, db) -> None:
    package = make_package(
        "tool", acl=[PackageACL(grantee_user_id="bob", role=ACLRole.READ, granted_by="alice")]
    )
    db.add(package)
    await db.commit()
    login_caller("alice", [])

    response = await http.get(f"/dashboard/{package.id}/share")

    assert response.status_code == 200
    assert "bob" in response.text


async def test_share_with_a_user_and_a_group(http, login_caller, mine, db) -> None:
    login_caller("alice", [])

    user = await http.post(
        f"/dashboard/{mine.id}/share", data={"grantee": " bob ", "grantee_type": "user"}
    )
    group = await http.post(
        f"/dashboard/{mine.id}/share",
        data={"grantee": "team:ops", "grantee_type": "group", "role": "write"},
    )

    assert user.status_code == group.status_code == 303
    rows = (await db.execute(select(PackageACL))).scalars().all()
    by_target = {(r.grantee_user_id, r.grantee_group): r for r in rows}
    assert by_target[("bob", None)].role == ACLRole.READ
    assert by_target[(None, "team:ops")].role == ACLRole.WRITE
    assert by_target[("bob", None)].granted_by == "alice"


async def test_duplicate_share_shows_an_error(http, login_caller, mine) -> None:
    login_caller("alice", [])
    data = {"grantee": "bob", "grantee_type": "user"}
    await http.post(f"/dashboard/{mine.id}/share", data=data)

    response = await http.post(f"/dashboard/{mine.id}/share", data=data)

    assert response.status_code == 409
    assert "already exists" in response.text


async def test_revoke_removes_the_grant(http, login_caller, mine, db) -> None:
    package_id = mine.id
    login_caller("alice", [])
    await http.post(
        f"/dashboard/{package_id}/share", data={"grantee": "bob", "grantee_type": "user"}
    )
    grant_id = (await db.execute(select(PackageACL))).scalar_one().id

    response = await http.post(f"/dashboard/{package_id}/revoke/{grant_id}")

    assert response.status_code == 303
    db.expire_all()
    assert (await db.execute(select(PackageACL))).scalars().all() == []
    assert (await http.post(f"/dashboard/{package_id}/revoke/{uuid.uuid4()}")).status_code == 404


async def test_write_grantee_can_manage_the_package(http, login_caller, db) -> None:
    package = make_package(
        "tool", acl=[PackageACL(grantee_user_id="bob", role=ACLRole.WRITE, granted_by="alice")]
    )
    db.add(package)
    await db.commit()
    login_caller("bob", [])

    assert (await http.get(f"/dashboard/{package.id}/share")).status_code == 200


async def test_read_grantee_cannot_manage_the_package(http, login_caller, db) -> None:
    package = make_package(
        "tool", acl=[PackageACL(grantee_user_id="bob", role=ACLRole.READ, granted_by="alice")]
    )
    db.add(package)
    await db.commit()
    login_caller("bob", [])

    assert (await http.get(f"/dashboard/{package.id}/share")).status_code == 403


async def test_package_page_offers_management_to_the_owner_only(http, login_caller, mine) -> None:
    login_caller("alice", [])
    owner_view = (await http.get(f"/packages/{mine.id}")).text
    login_caller("admin", ["apt:admin"])
    admin_view = (await http.get(f"/packages/{mine.id}")).text

    assert f"/dashboard/{mine.id}/share" in owner_view
    assert f"/dashboard/{mine.id}/delete" in admin_view


@pytest.fixture
def notifications(monkeypatch):
    sent: list[dict] = []

    async def record(**kwargs) -> None:
        sent.append(kwargs)

    from apt_server.services import email

    monkeypatch.setattr(email, "send_package_shared", record)
    return sent


async def test_sharing_with_an_email_notifies_the_grantee(
    http, login_caller, mine, notifications
) -> None:
    login_caller("alice", [], display_name="alice@example.com")

    await http.post(
        f"/dashboard/{mine.id}/share",
        data={"grantee": "bob@example.com", "grantee_type": "user", "role": "write"},
    )

    (message,) = notifications
    assert message["to_email"] == "bob@example.com"
    assert message["to_name"] == "bob"
    assert message["sharer"] == "alice@example.com"
    assert message["role"] == "write"
    assert message["package_name"] == "tool"
    assert message["package_url"] == f"https://test/packages/{mine.id}"


async def test_sharing_with_a_group_or_an_opaque_id_sends_nothing(
    http, login_caller, mine, notifications
) -> None:
    login_caller("alice", [])

    await http.post(
        f"/dashboard/{mine.id}/share", data={"grantee": "team:ops", "grantee_type": "group"}
    )
    await http.post(
        f"/dashboard/{mine.id}/share", data={"grantee": "sub-123", "grantee_type": "user"}
    )

    assert notifications == []


async def test_a_rejected_duplicate_grant_does_not_notify_again(
    http, login_caller, mine, notifications
) -> None:
    login_caller("alice", [])
    data = {"grantee": "bob@example.com", "grantee_type": "user"}

    await http.post(f"/dashboard/{mine.id}/share", data=data)
    await http.post(f"/dashboard/{mine.id}/share", data=data)

    assert len(notifications) == 1
