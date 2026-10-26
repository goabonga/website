# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Build minimal but valid ``.deb`` archives without ``dpkg-deb``."""

import io
import tarfile
import time


def _tar_gz(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _ar_member(name: str, content: bytes) -> bytes:
    header = f"{name + '/':<16}{int(time.time()):<12}{0:<6}{0:<6}{'100644':<8}{len(content):<10}`\n"
    padding = b"\n" if len(content) % 2 else b""
    return header.encode() + content + padding


def build_deb(
    name: str = "demo",
    version: str = "1.0",
    architecture: str = "amd64",
    description: str = "demo package",
    extra_control: dict[str, str] | None = None,
) -> bytes:
    """Return the bytes of a ``.deb`` whose control stanza uses the given fields."""
    fields = {
        "Package": name,
        "Version": version,
        "Architecture": architecture,
        "Maintainer": "Test <test@example.com>",
        "Description": description,
        **(extra_control or {}),
    }
    control = "".join(f"{key}: {value}\n" for key, value in fields.items() if value is not None)
    return (
        b"!<arch>\n"
        + _ar_member("debian-binary", b"2.0\n")
        + _ar_member("control.tar.gz", _tar_gz({"./control": control.encode()}))
        + _ar_member("data.tar.gz", _tar_gz({"./usr/share/demo": b"hello"}))
    )
