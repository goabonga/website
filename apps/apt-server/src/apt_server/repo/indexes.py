# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Render ``Packages`` indexes from database rows.

The Debian ``Packages`` file is a concatenation of RFC 822-style stanzas, one
per package version. Each stanza carries the control fields verbatim plus the
``Filename``, ``Size`` and hash headers that tell apt where to download the
``.deb`` and how to verify it.

All rendering happens from the ``packages`` table: a package that is not in
the caller's visible set is simply absent from their ``Packages`` file.
"""

import gzip
from collections.abc import Iterable, Sequence

from apt_server.db.models import Package

_PREFERRED_ORDER: Sequence[str] = (
    "Package",
    "Source",
    "Version",
    "Architecture",
    "Section",
    "Priority",
    "Essential",
    "Origin",
    "Maintainer",
    "Installed-Size",
    "Provides",
    "Pre-Depends",
    "Depends",
    "Recommends",
    "Suggests",
    "Conflicts",
    "Breaks",
    "Replaces",
    "Enhances",
    "Homepage",
    "Description",
)

_SKIP_CONTROL_KEYS = {"Filename", "Size", "MD5sum", "SHA1", "SHA256"}


def render_stanza(package: Package) -> str:
    """Render a single package stanza exactly as apt expects it.

    Ordering puts the usual control fields first (same order as ``dpkg-deb
    --field``) and appends any extra keys in alphabetical order, then the
    repository-computed headers (Filename, Size, hashes) last.
    """
    control = dict(package.control)
    lines: list[str] = []

    seen: set[str] = set()
    for key in _PREFERRED_ORDER:
        if key in control:
            lines.append(f"{key}: {control[key]}")
            seen.add(key)

    for key in sorted(control):
        if key in seen or key in _SKIP_CONTROL_KEYS:
            continue
        lines.append(f"{key}: {control[key]}")

    lines.append(f"Filename: {package.filename}")
    lines.append(f"Size: {package.size}")
    lines.append(f"MD5sum: {package.md5}")
    lines.append(f"SHA1: {package.sha1}")
    lines.append(f"SHA256: {package.sha256}")
    return "\n".join(lines) + "\n"


def render_packages_file(packages: Iterable[Package]) -> bytes:
    """Concatenate stanzas into a full ``Packages`` file (UTF-8 encoded)."""
    stanzas = [render_stanza(pkg) for pkg in packages]
    return "\n".join(stanzas).encode("utf-8")


def gzip_packages(body: bytes) -> bytes:
    """Gzip a ``Packages`` file body (no filename or timestamp in the header)."""
    return gzip.compress(body, mtime=0)
