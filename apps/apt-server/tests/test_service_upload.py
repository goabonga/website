# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Upload orchestration: parse, validate, store and persist."""

import pytest
from apt_server.acl.packages import Caller
from apt_server.db.models import IndexCache, Package, PackageVisibility
from apt_server.services.upload import UploadConflictError, UploadValidationError, save_upload
from debfactory import build_deb
from sqlalchemy import select

ALICE = Caller(sub="alice")


async def upload(db, raw=None, **kwargs):
    kwargs.setdefault("suite", "stable")
    kwargs.setdefault("component", "main")
    return await save_upload(db, caller=ALICE, raw_body=raw or build_deb(), **kwargs)


async def test_upload_persists_the_package_and_stores_the_file(db, repo_root) -> None:
    package = await upload(db)

    assert (package.name, package.version, package.architecture) == ("demo", "1.0", "amd64")
    assert package.owner_id == "alice"
    assert package.visibility == PackageVisibility.PRIVATE
    assert package.filename == "pool/main/d/demo/demo_1.0_amd64.deb"
    assert package.control["Maintainer"] == "Test <test@example.com>"
    stored = repo_root / package.filename
    assert stored.is_file()
    assert stored.stat().st_size == package.size


async def test_upload_honours_the_requested_visibility(db, repo_root) -> None:
    package = await upload(db, visibility=PackageVisibility.PUBLIC)

    assert package.visibility == PackageVisibility.PUBLIC


async def test_architecture_all_is_accepted(db, repo_root) -> None:
    package = await upload(db, build_deb(architecture="all"))

    assert package.architecture == "all"


async def test_upload_invalidates_the_index_cache(db, repo_root) -> None:
    db.add(IndexCache(cache_key="k", body=b"old", sha256="0" * 64))
    await db.commit()

    await upload(db)

    assert (await db.execute(select(IndexCache))).scalars().all() == []


async def test_invalid_archive_is_rejected_before_any_write(db, repo_root) -> None:
    with pytest.raises(UploadValidationError, match="failed to parse"):
        await upload(db, b"garbage")

    assert not any(repo_root.rglob("*.deb"))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"component": "rogue"}, "unknown component"),
        ({"suite": "rogue"}, "unknown suite"),
    ],
)
async def test_unknown_component_or_suite_is_rejected(db, repo_root, kwargs, message) -> None:
    with pytest.raises(UploadValidationError, match=message):
        await upload(db, **kwargs)


async def test_unsupported_architecture_is_rejected(db, repo_root) -> None:
    with pytest.raises(UploadValidationError, match="unsupported architecture"):
        await upload(db, build_deb(architecture="riscv64"))


async def test_duplicate_identity_is_a_conflict(db, repo_root) -> None:
    first = await upload(db)

    with pytest.raises(UploadConflictError) as info:
        await upload(db)

    assert info.value.existing.id == first.id


async def test_same_package_can_live_in_another_component(db, repo_root) -> None:
    await upload(db)
    other = await upload(db, component="private")

    assert other.filename.startswith("pool/private/")
    assert len((await db.execute(select(Package))).scalars().all()) == 2


async def test_temporary_files_are_cleaned_up(db, repo_root, tmp_path, monkeypatch) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()

    await upload(db)
    with pytest.raises(UploadConflictError):
        await upload(db)

    assert list((tmp_path / "tmp").iterdir()) == []
