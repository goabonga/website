# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pool storage on disk."""

import pytest
from apt_server.config import settings
from apt_server.repo import pool
from apt_server.repo.debfile import DebMetadata


@pytest.fixture(autouse=True)
def repo_root(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(settings, "apt_repo_root", str(root))
    return root


def metadata(name="demo", sha256="a" * 64) -> DebMetadata:
    return DebMetadata(name, "1.0", "amd64", "", {}, 3, "", "", sha256)


def staged(tmp_path, content=b"abc", name="staged.deb"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_relative_path_follows_the_pool_layout() -> None:
    assert pool.pool_relative_path(metadata(), "main") == "pool/main/d/demo/demo_1.0_amd64.deb"
    assert (
        pool.pool_relative_path(metadata("libfoo"), "private")
        == "pool/private/libf/libfoo/libfoo_1.0_amd64.deb"
    )


def test_absolute_path_is_under_the_repository_root(repo_root) -> None:
    assert pool.repo_root() == repo_root
    assert pool.pool_absolute_path(metadata(), "main") == (
        repo_root / "pool/main/d/demo/demo_1.0_amd64.deb"
    )


def test_write_moves_the_staged_file_into_the_pool(tmp_path, repo_root) -> None:
    source = staged(tmp_path)

    destination = pool.write_deb(source, metadata(), "main")

    assert destination.read_bytes() == b"abc"
    assert not source.exists()
    assert destination == repo_root / "pool/main/d/demo/demo_1.0_amd64.deb"


def test_writing_identical_content_twice_is_idempotent(tmp_path) -> None:
    import hashlib

    digest = hashlib.sha256(b"abc").hexdigest()
    pool.write_deb(staged(tmp_path), metadata(sha256=digest), "main")
    second = staged(tmp_path, name="again.deb")

    destination = pool.write_deb(second, metadata(sha256=digest), "main")

    assert destination.read_bytes() == b"abc"
    assert not second.exists()


def test_writing_different_content_is_a_collision(tmp_path) -> None:
    pool.write_deb(staged(tmp_path), metadata(), "main")

    with pytest.raises(FileExistsError, match="pool collision"):
        pool.write_deb(staged(tmp_path, b"other", "other.deb"), metadata(), "main")


def test_delete_removes_the_file_and_tolerates_absence(tmp_path) -> None:
    destination = pool.write_deb(staged(tmp_path), metadata(), "main")
    relative = pool.pool_relative_path(metadata(), "main")

    pool.delete_deb(relative)
    pool.delete_deb(relative)

    assert not destination.exists()
