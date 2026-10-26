# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Chunked file upload manager.

Handles multi-part uploads where the client sends a file in sequential
chunks. Each upload session is identified by an ``upload_id`` (UUID)
and tracked by a JSON manifest on disk alongside the chunk files.

Flow:
1. ``POST /api/upload/init`` → create session, return ``upload_id``.
2. ``POST /api/upload/{upload_id}/chunk?index=N`` → append chunk N.
3. ``POST /api/upload/{upload_id}/complete`` → assemble, parse, persist.

Orphaned sessions (older than ``UPLOAD_TTL``) are cleaned up lazily on
the next init call.
"""

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from apt_server.config import settings


def _uploads_dir() -> Path:
    base = Path(settings.apt_repo_root) / ".uploads"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _session_dir(upload_id: str) -> Path:
    return _uploads_dir() / upload_id


def _manifest_path(upload_id: str) -> Path:
    return _session_dir(upload_id) / "manifest.json"


def create_session(
    *,
    filename: str,
    total_size: int,
    total_chunks: int,
    owner_id: str,
    suite: str,
    component: str,
    visibility: str,
) -> str:
    """Create a new upload session and return its ID."""
    if total_size > settings.upload_max_size:
        raise ValueError(f"file too large: {total_size} > {settings.upload_max_size}")

    upload_id = str(uuid.uuid4())
    session_dir = _session_dir(upload_id)
    session_dir.mkdir(parents=True)

    manifest = {
        "upload_id": upload_id,
        "filename": filename,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "received_chunks": [],
        "owner_id": owner_id,
        "suite": suite,
        "component": component,
        "visibility": visibility,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _manifest_path(upload_id).write_text(json.dumps(manifest))

    _cleanup_orphaned()
    return upload_id


def save_chunk(upload_id: str, index: int, data: bytes) -> dict:
    """Write a chunk to disk and update the manifest.

    Returns the updated manifest dict.
    """
    manifest = _read_manifest(upload_id)
    if index < 0 or index >= manifest["total_chunks"]:
        raise ValueError(f"chunk index {index} out of range [0, {manifest['total_chunks']})")
    if index in manifest["received_chunks"]:
        raise ValueError(f"chunk {index} already received")

    chunk_path = _session_dir(upload_id) / f"chunk_{index:06d}"
    chunk_path.write_bytes(data)

    manifest["received_chunks"].append(index)
    manifest["received_chunks"].sort()
    _manifest_path(upload_id).write_text(json.dumps(manifest))
    return manifest


def assemble(upload_id: str) -> tuple[Path, dict]:
    """Concatenate all chunks into a single file.

    Returns ``(assembled_path, manifest)`` ready for ``save_upload``.
    Raises ``ValueError`` if chunks are missing.
    """
    manifest = _read_manifest(upload_id)
    expected = list(range(manifest["total_chunks"]))
    if manifest["received_chunks"] != expected:
        missing = set(expected) - set(manifest["received_chunks"])
        raise ValueError(f"missing chunks: {sorted(missing)}")

    assembled = _session_dir(upload_id) / manifest["filename"]
    with assembled.open("wb") as out:
        for i in expected:
            chunk_path = _session_dir(upload_id) / f"chunk_{i:06d}"
            out.write(chunk_path.read_bytes())

    return assembled, manifest


def delete_session(upload_id: str) -> None:
    """Remove a session directory and all its chunks."""
    session_dir = _session_dir(upload_id)
    if session_dir.exists():
        shutil.rmtree(session_dir)


def get_manifest(upload_id: str) -> dict:
    """Return the manifest for a session, or raise ValueError."""
    return _read_manifest(upload_id)


def _read_manifest(upload_id: str) -> dict:
    path = _manifest_path(upload_id)
    if not path.exists():
        raise ValueError(f"upload session not found: {upload_id}")
    return json.loads(path.read_text())


def _cleanup_orphaned() -> None:
    """Remove upload sessions older than UPLOAD_TTL."""
    uploads_dir = _uploads_dir()
    cutoff = datetime.now(UTC).timestamp() - settings.upload_ttl
    for session_dir in uploads_dir.iterdir():
        if not session_dir.is_dir():
            continue
        manifest_path = session_dir / "manifest.json"
        if not manifest_path.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
            created = datetime.fromisoformat(manifest["created_at"]).timestamp()
            if created < cutoff:
                shutil.rmtree(session_dir, ignore_errors=True)
        except (json.JSONDecodeError, KeyError, ValueError):
            shutil.rmtree(session_dir, ignore_errors=True)
