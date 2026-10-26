# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Package, ACL and index cache models."""

import uuid

import pytest
from apt_server.db.models import (
    ACLRole,
    Base,
    IndexCache,
    Package,
    PackageACL,
    PackageVisibility,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload


def make_package(**overrides) -> Package:
    values = {
        "name": "demo",
        "version": "1.0",
        "architecture": "amd64",
        "suite": "stable",
        "component": "main",
        "owner_id": "alice",
        "filename": "pool/main/d/demo/demo_1.0_amd64.deb",
        "size": 10,
        "md5": "0" * 32,
        "sha1": "1" * 40,
        "sha256": "2" * 64,
        **overrides,
    }
    return Package(**values)


def test_metadata_declares_the_catalog_tables() -> None:
    assert {"packages", "package_acl", "index_cache"} <= set(Base.metadata.tables)


async def test_package_defaults(db) -> None:
    package = make_package()
    db.add(package)
    await db.commit()

    stored = (await db.execute(select(Package))).scalar_one()
    assert isinstance(stored.id, uuid.UUID)
    assert stored.visibility == PackageVisibility.PRIVATE
    assert stored.control == {}
    assert stored.uploaded_at is not None
    assert "demo 1.0 amd64 main" in repr(stored)


async def test_package_identity_is_unique(db) -> None:
    db.add(make_package())
    await db.commit()
    db.add(make_package(filename="pool/main/d/demo/other.deb"))

    with pytest.raises(IntegrityError):
        await db.commit()


async def test_package_filename_is_unique(db) -> None:
    db.add(make_package())
    await db.commit()
    db.add(make_package(version="2.0"))

    with pytest.raises(IntegrityError):
        await db.commit()


async def test_control_fields_are_stored_as_json(db) -> None:
    db.add(make_package(control={"Package": "demo", "Depends": "libc6"}))
    await db.commit()

    stored = (await db.execute(select(Package))).scalar_one()
    assert stored.control == {"Package": "demo", "Depends": "libc6"}


async def test_acl_entries_belong_to_a_package_and_cascade(db) -> None:
    package = make_package()
    package.acl.append(PackageACL(grantee_user_id="bob", role=ACLRole.READ, granted_by="alice"))
    package.acl.append(PackageACL(grantee_group="team:ops", role=ACLRole.WRITE, granted_by="alice"))
    db.add(package)
    await db.commit()

    stored = (await db.execute(select(Package).options(selectinload(Package.acl)))).scalar_one()
    assert {entry.role for entry in stored.acl} == {ACLRole.READ, ACLRole.WRITE}
    assert "bob" in repr(stored.acl[0]) or "bob" in repr(stored.acl[1])

    await db.delete(stored)
    await db.commit()
    assert (await db.execute(select(PackageACL))).scalars().all() == []


@pytest.mark.parametrize(
    "grantee",
    [{}, {"grantee_user_id": "bob", "grantee_group": "team"}],
    ids=["no grantee", "two grantees"],
)
async def test_acl_requires_exactly_one_grantee(db, grantee) -> None:
    package = make_package()
    package.acl.append(PackageACL(role=ACLRole.READ, granted_by="alice", **grantee))
    db.add(package)

    with pytest.raises(IntegrityError):
        await db.commit()


async def test_acl_grants_are_unique_per_package_grantee_and_role(db) -> None:
    package = make_package()
    for _ in range(2):
        package.acl.append(PackageACL(grantee_user_id="bob", role=ACLRole.READ, granted_by="a"))
    db.add(package)

    with pytest.raises(IntegrityError):
        await db.commit()


async def test_index_cache_row_round_trip(db) -> None:
    db.add(IndexCache(cache_key="k" * 64, body=b"Package: demo\n", sha256="3" * 64))
    await db.commit()

    stored = await db.get(IndexCache, "k" * 64)
    assert stored.body == b"Package: demo\n"
    assert stored.generated_at is not None
    assert "k" * 64 in repr(stored)
