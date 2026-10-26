# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Per-caller index rendering and caching backed by the database."""

from datetime import UTC, datetime, timedelta

import pytest
from apt_server.acl.packages import Caller
from apt_server.config import settings
from apt_server.db.models import IndexCache, Package, PackageVisibility
from apt_server.services import indexes as index_service
from sqlalchemy import func, select


def make_package(name: str, visibility: PackageVisibility, component: str = "main", **extra):
    return Package(
        name=name,
        version="1.0",
        architecture=extra.pop("architecture", "amd64"),
        suite="stable",
        component=component,
        owner_id=extra.pop("owner_id", "alice"),
        visibility=visibility,
        filename=f"pool/{component}/{name[0]}/{name}/{name}_1.0.deb",
        size=1,
        md5="0" * 32,
        sha1="1" * 40,
        sha256="2" * 64,
        control={"Package": name, "Version": "1.0", "Architecture": "amd64"},
    )


@pytest.fixture(autouse=True)
def repository_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "apt_components", "main,private")
    monkeypatch.setattr(settings, "apt_public_components", "main")
    monkeypatch.setattr(settings, "apt_architectures", "amd64")
    monkeypatch.setattr(settings, "apt_suites", "stable")
    monkeypatch.setattr(settings, "apt_index_cache_ttl", 60)


@pytest.fixture
async def catalog(db):
    db.add_all(
        [
            make_package("pub", PackageVisibility.PUBLIC),
            make_package("priv", PackageVisibility.PRIVATE, owner_id="bob"),
            make_package("arch-all", PackageVisibility.PUBLIC, architecture="all"),
            make_package("hidden", PackageVisibility.PRIVATE, component="private"),
            make_package("open-private", PackageVisibility.PUBLIC, component="private"),
        ]
    )
    await db.commit()
    return db


async def packages(db, caller, **kwargs) -> str:
    body = await index_service.render_packages(
        db, caller, suite="stable", component=kwargs.pop("component", "main"),
        architecture="amd64", **kwargs,
    )  # fmt: skip
    return body.decode() if not kwargs.get("gzip") else body


def test_cache_key_depends_on_caller_and_variant() -> None:
    args = {"suite": "stable", "component": "main", "architecture": "amd64", "gzip": False}
    alice = Caller(sub="alice")

    assert index_service.cache_key(alice, **args) == index_service.cache_key(alice, **args)
    assert index_service.cache_key(alice, **args) != index_service.cache_key(None, **args)
    assert index_service.cache_key(alice, **args) != index_service.cache_key(
        Caller(sub="bob"), **args
    )
    assert index_service.cache_key(alice, **args) != index_service.cache_key(
        alice, **{**args, "gzip": True}
    )
    assert index_service.cache_key(alice, **args) != index_service.cache_key(
        Caller(sub="alice", groups=frozenset({"g"})), **args
    )
    assert len(index_service.cache_key(None, **args)) == 64


async def test_anonymous_index_lists_public_packages_only(catalog) -> None:
    text = await packages(catalog, None)

    assert "Package: pub\n" in text
    assert "Package: arch-all\n" in text
    assert "priv" not in text


async def test_owner_index_includes_private_packages(catalog) -> None:
    text = await packages(catalog, Caller(sub="bob"))

    assert "Package: priv\n" in text
    assert "Package: pub\n" in text


async def test_index_is_filtered_by_component(catalog) -> None:
    text = await packages(catalog, None, component="private")

    assert "Package: open-private\n" in text
    assert "hidden" not in text and "Package: pub\n" not in text


async def test_index_is_sorted_by_name(catalog) -> None:
    text = await packages(catalog, None)

    assert text.index("Package: arch-all") < text.index("Package: pub")


async def test_gzip_index_decompresses_to_the_plain_index(catalog) -> None:
    import gzip

    plain = await index_service.render_packages(
        catalog, None, suite="stable", component="main", architecture="amd64"
    )
    zipped = await index_service.render_packages(
        catalog, None, suite="stable", component="main", architecture="amd64", gzip=True
    )

    assert gzip.decompress(zipped) == plain


async def test_rendered_index_is_cached_until_invalidated(catalog) -> None:
    first = await packages(catalog, None)
    catalog.add(make_package("later", PackageVisibility.PUBLIC))
    await catalog.commit()

    assert await packages(catalog, None) == first

    await index_service.invalidate_index_cache(catalog)
    await catalog.commit()

    assert "Package: later\n" in await packages(catalog, None)


async def test_cache_entries_expire_after_the_ttl(catalog, monkeypatch) -> None:
    await packages(catalog, None)
    row = (await catalog.execute(select(IndexCache))).scalars().first()
    row.generated_at = datetime.now(UTC) - timedelta(seconds=120)
    await catalog.commit()
    catalog.add(make_package("later", PackageVisibility.PUBLIC))
    await catalog.commit()

    assert "Package: later\n" in await packages(catalog, None)


async def test_zero_ttl_never_expires(catalog, monkeypatch) -> None:
    monkeypatch.setattr(settings, "apt_index_cache_ttl", 0)
    await packages(catalog, None)
    row = (await catalog.execute(select(IndexCache))).scalars().first()
    row.generated_at = datetime.now(UTC) - timedelta(days=30)
    await catalog.commit()
    catalog.add(make_package("later", PackageVisibility.PUBLIC))
    await catalog.commit()

    assert "Package: later\n" not in await packages(catalog, None)


async def test_cache_holds_one_row_per_caller_and_variant(catalog) -> None:
    await packages(catalog, None)
    await packages(catalog, Caller(sub="bob"))
    await packages(catalog, None, gzip=True)

    count = (await catalog.execute(select(func.count()).select_from(IndexCache))).scalar()
    assert count == 3


async def test_release_for_anonymous_hides_private_components(catalog) -> None:
    text = (await index_service.render_release(catalog, None, suite="stable")).decode()

    assert "Components: main\n" in text
    assert "main/binary-amd64/Packages.gz" in text
    assert "private/" not in text


async def test_release_for_authenticated_caller_adds_components_with_visible_packages(
    catalog,
) -> None:
    text = (
        await index_service.render_release(catalog, Caller(sub="alice"), suite="stable")
    ).decode()

    assert "Components: main private\n" in text
    assert "private/binary-amd64/Packages" in text


async def test_release_hides_private_components_without_visible_packages(db) -> None:
    db.add(make_package("hidden", PackageVisibility.PRIVATE, component="private"))
    await db.commit()

    text = (await index_service.render_release(db, Caller(sub="bob"), suite="stable")).decode()

    assert "Components: main\n" in text
    assert "private/" not in text
