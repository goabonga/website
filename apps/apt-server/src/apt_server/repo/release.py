# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Render and sign ``Release`` / ``InRelease`` files.

A ``Release`` file is an RFC 822-style document that lists the repository
origin, suite, supported components and architectures, and for every
``Packages`` variant the MD5/SHA-1/SHA-256 checksum plus byte size. APT
clients refuse to install from a repository whose ``Release`` is unsigned
(or signed by an untrusted key), so we sign the file in two forms:

- ``InRelease`` — clear-signed (signature inside the body). Preferred by
  modern apt, fetched in a single request.
- ``Release.gpg`` — detached signature accompanying the plain ``Release``.
  Kept for backward compatibility with older clients.

Signing is delegated to a local ``gpg`` binary so the private key material
never reaches Python. When ``APT_GPG_KEY_ID`` is empty we return the plain
``Release`` body in both slots — useful for tests and local dev, never for
production.
"""

import hashlib
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from apt_server.config import settings


@dataclass(slots=True, frozen=True)
class IndexChecksum:
    """Hashes and size of a ``Packages`` / ``Packages.gz`` file."""

    relative_path: str  # e.g. "main/binary-amd64/Packages"
    size: int
    md5: str
    sha1: str
    sha256: str


def index_checksum(relative_path: str, body: bytes) -> IndexChecksum:
    """Compute the checksums needed for a ``Release`` stanza."""
    return IndexChecksum(
        relative_path=relative_path,
        size=len(body),
        md5=hashlib.md5(body).hexdigest(),
        sha1=hashlib.sha1(body).hexdigest(),
        sha256=hashlib.sha256(body).hexdigest(),
    )


def render_release(
    *,
    suite: str,
    components: list[str],
    architectures: list[str],
    indexes: Mapping[str, bytes],
) -> bytes:
    """Render a plain ``Release`` body.

    ``indexes`` maps ``<component>/binary-<arch>/<Packages|Packages.gz>`` to
    its raw bytes. Every file listed under MD5Sum/SHA1/SHA256 must exist in
    the map, otherwise apt rejects the release.
    """
    now = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S UTC")
    header = [
        f"Origin: {settings.apt_origin}",
        f"Label: {settings.apt_label}",
        f"Suite: {suite}",
        f"Codename: {suite}",
        f"Date: {now}",
        f"Architectures: {' '.join(architectures)}",
        f"Components: {' '.join(components)}",
        "Description: packages served by apt-server",
    ]

    checksums = [index_checksum(path, body) for path, body in sorted(indexes.items())]

    md5_lines = [" " + _checksum_line(c.md5, c.size, c.relative_path) for c in checksums]
    sha1_lines = [" " + _checksum_line(c.sha1, c.size, c.relative_path) for c in checksums]
    sha256_lines = [" " + _checksum_line(c.sha256, c.size, c.relative_path) for c in checksums]

    body = "\n".join(
        [
            *header,
            "MD5Sum:",
            *md5_lines,
            "SHA1:",
            *sha1_lines,
            "SHA256:",
            *sha256_lines,
        ]
    )
    return (body + "\n").encode("utf-8")


def _checksum_line(digest: str, size: int, path: str) -> str:
    return f"{digest} {size:>16} {path}"


def sign_clearsigned(release: bytes) -> bytes:
    """Return ``InRelease`` (clear-signed ``Release``)."""
    if not settings.apt_gpg_key_id:
        return release
    return _run_gpg(["--clearsign", "--local-user", settings.apt_gpg_key_id], release)


def sign_detached(release: bytes) -> bytes:
    """Return ``Release.gpg`` (detached ASCII-armored signature)."""
    if not settings.apt_gpg_key_id:
        return b""
    return _run_gpg(
        ["--detach-sign", "--armor", "--local-user", settings.apt_gpg_key_id],
        release,
    )


def _run_gpg(extra_args: list[str], body: bytes) -> bytes:
    cmd = ["/usr/bin/gpg", "--batch", "--yes", "--pinentry-mode", "loopback", *extra_args]
    completed = subprocess.run(
        cmd,
        input=body,
        capture_output=True,
        check=True,
    )
    return completed.stdout
