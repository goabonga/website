# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Per-package access control: visibility filter, read and write checks."""

import pytest
from apt_server.acl.packages import Caller, can_read, can_write, visible_package_filter
from apt_server.db.models import ACLRole, Package, PackageACL, PackageVisibility
from sqlalchemy import select


def package(name: str, visibility: PackageVisibility, owner: str = "alice", acl=()) -> Package:
    pkg = Package(
        name=name,
        version="1.0",
        architecture="amd64",
        suite="stable",
        component="main",
        owner_id=owner,
        visibility=visibility,
        filename=f"pool/main/{name[0]}/{name}/{name}_1.0_amd64.deb",
        size=1,
        md5="0" * 32,
        sha1="1" * 40,
        sha256="2" * 64,
    )
    pkg.acl.extend(acl)
    return pkg


def grant(role=ACLRole.READ, user=None, group=None) -> PackageACL:
    return PackageACL(grantee_user_id=user, grantee_group=group, role=role, granted_by="alice")


ADMIN = Caller(sub="root", scopes=frozenset({"apt:admin"}))
BOB = Caller(sub="bob-sub", display_name="bob@example.com")


def test_caller_is_admin_only_with_admin_scope() -> None:
    assert ADMIN.is_admin
    assert not Caller(sub="x", scopes=frozenset({"apt:write"})).is_admin


def test_public_packages_are_readable_by_everyone() -> None:
    pub = package("pub", PackageVisibility.PUBLIC)

    assert can_read(None, pub)
    assert can_read(BOB, pub)
    assert not can_write(None, pub)
    assert not can_write(BOB, pub)


def test_private_packages_need_ownership_grant_or_admin() -> None:
    priv = package("priv", PackageVisibility.PRIVATE)

    assert not can_read(None, priv)
    assert not can_read(BOB, priv)
    assert can_read(Caller(sub="alice"), priv)
    assert can_read(ADMIN, priv)


def test_owner_and_admin_can_write() -> None:
    priv = package("priv", PackageVisibility.PRIVATE)

    assert can_write(Caller(sub="alice"), priv)
    assert can_write(ADMIN, priv)
    assert not can_write(BOB, priv)


def test_read_grant_allows_reading_but_not_writing() -> None:
    shared = package("shared", PackageVisibility.SHARED, acl=[grant(user="bob-sub")])

    assert can_read(BOB, shared)
    assert not can_write(BOB, shared)


def test_write_grant_allows_reading_and_writing() -> None:
    shared = package("shared", PackageVisibility.SHARED, acl=[grant(ACLRole.WRITE, user="bob-sub")])

    assert can_read(BOB, shared)
    assert can_write(BOB, shared)


def test_grants_match_the_caller_email() -> None:
    shared = package("shared", PackageVisibility.SHARED, acl=[grant(user="bob@example.com")])

    assert can_read(BOB, shared)
    assert not can_read(Caller(sub="eve", display_name="eve@example.com"), shared)


def test_grants_match_caller_groups() -> None:
    shared = package("shared", PackageVisibility.SHARED, acl=[grant(group="team:ops")])
    member = Caller(sub="carol", groups=frozenset({"team:ops"}))

    assert can_read(member, shared)
    assert not can_read(Caller(sub="dave", groups=frozenset({"team:dev"})), shared)


@pytest.fixture
async def catalog(db):
    pub = package("pub", PackageVisibility.PUBLIC)
    own = package("own", PackageVisibility.PRIVATE, owner="bob-sub")
    other = package("other", PackageVisibility.PRIVATE, owner="alice")
    by_sub = package("bysub", PackageVisibility.SHARED, acl=[grant(user="bob-sub")])
    by_mail = package("bymail", PackageVisibility.SHARED, acl=[grant(user="bob@example.com")])
    by_group = package("bygroup", PackageVisibility.SHARED, acl=[grant(group="team:ops")])
    db.add_all([pub, own, other, by_sub, by_mail, by_group])
    await db.commit()
    return db


async def visible(db, caller) -> set[str]:
    rows = await db.execute(select(Package.name).where(visible_package_filter(caller)))
    return set(rows.scalars())


async def test_anonymous_filter_keeps_public_only(catalog) -> None:
    assert await visible(catalog, None) == {"pub"}


async def test_authenticated_filter_adds_owned_and_granted(catalog) -> None:
    assert await visible(catalog, BOB) == {"pub", "own", "bysub", "bymail"}


async def test_group_membership_extends_the_filter(catalog) -> None:
    ops = Caller(sub="carol", groups=frozenset({"team:ops"}))

    assert await visible(catalog, ops) == {"pub", "bygroup"}


async def test_admin_filter_sees_everything(catalog) -> None:
    assert len(await visible(catalog, ADMIN)) == 6
