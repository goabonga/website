# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Chunked upload sessions kept on disk."""

import json
import os
from datetime import UTC, datetime, timedelta

import pytest
from apt_server.config import settings
from apt_server.services import chunked_upload as uploads


@pytest.fixture(autouse=True)
def storage(repo_root, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_size", 1000)
    monkeypatch.setattr(settings, "upload_ttl", 3600)
    return repo_root


def new_session(**overrides) -> str:
    values = {
        "filename": "demo.deb",
        "total_size": 6,
        "total_chunks": 2,
        "owner_id": "alice",
        "suite": "stable",
        "component": "main",
        "visibility": "private",
        **overrides,
    }
    return uploads.create_session(**values)


def test_create_session_writes_a_manifest(storage) -> None:
    upload_id = new_session()

    manifest = uploads.get_manifest(upload_id)
    assert manifest["upload_id"] == upload_id
    assert manifest["received_chunks"] == []
    assert manifest["owner_id"] == "alice"
    assert (storage / ".uploads" / upload_id / "manifest.json").is_file()


def test_create_session_rejects_oversized_files() -> None:
    with pytest.raises(ValueError, match="too large"):
        new_session(total_size=1001)


def test_unknown_session_is_reported() -> None:
    with pytest.raises(ValueError, match="not found"):
        uploads.get_manifest("nope")


def test_chunks_are_recorded_in_order_of_index() -> None:
    upload_id = new_session()

    uploads.save_chunk(upload_id, 1, b"def")
    manifest = uploads.save_chunk(upload_id, 0, b"abc")

    assert manifest["received_chunks"] == [0, 1]


@pytest.mark.parametrize("index", [-1, 2])
def test_chunk_index_must_be_in_range(index) -> None:
    upload_id = new_session()

    with pytest.raises(ValueError, match="out of range"):
        uploads.save_chunk(upload_id, index, b"x")


def test_a_chunk_cannot_be_sent_twice() -> None:
    upload_id = new_session()
    uploads.save_chunk(upload_id, 0, b"abc")

    with pytest.raises(ValueError, match="already received"):
        uploads.save_chunk(upload_id, 0, b"abc")


def test_assemble_concatenates_chunks_in_order() -> None:
    upload_id = new_session()
    uploads.save_chunk(upload_id, 1, b"def")
    uploads.save_chunk(upload_id, 0, b"abc")

    path, manifest = uploads.assemble(upload_id)

    assert path.name == "demo.deb"
    assert path.read_bytes() == b"abcdef"
    assert manifest["filename"] == "demo.deb"


def test_assemble_reports_missing_chunks() -> None:
    upload_id = new_session()
    uploads.save_chunk(upload_id, 0, b"abc")

    with pytest.raises(ValueError, match=r"missing chunks: \[1\]"):
        uploads.assemble(upload_id)


def test_delete_session_removes_its_directory(storage) -> None:
    upload_id = new_session()

    uploads.delete_session(upload_id)
    uploads.delete_session(upload_id)

    assert not (storage / ".uploads" / upload_id).exists()


def test_expired_sessions_are_cleaned_when_a_new_one_starts(storage) -> None:
    old = new_session()
    manifest_path = storage / ".uploads" / old / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["created_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    manifest_path.write_text(json.dumps(manifest))
    fresh = new_session()

    third = new_session()

    assert not (storage / ".uploads" / old).exists()
    assert (storage / ".uploads" / fresh).exists()
    assert (storage / ".uploads" / third).exists()


def test_broken_sessions_are_cleaned(storage) -> None:
    (storage / ".uploads").mkdir()
    (storage / ".uploads" / "no-manifest").mkdir()
    corrupt = storage / ".uploads" / "corrupt"
    corrupt.mkdir()
    (corrupt / "manifest.json").write_text("{not json")
    (storage / ".uploads" / "stray-file").write_text("x")

    new_session()

    assert not (storage / ".uploads" / "no-manifest").exists()
    assert not corrupt.exists()
    assert (storage / ".uploads" / "stray-file").exists()


def test_uploads_directory_lives_in_the_repository_root(storage) -> None:
    new_session()

    assert os.path.isdir(storage / ".uploads")
