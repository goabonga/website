# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Parse Debian package metadata from uploaded ``.deb`` files."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from debian.debfile import DebFile


class InvalidDebFileError(ValueError):
    """Raised when the uploaded file cannot be parsed as a Debian package."""


@dataclass(slots=True, frozen=True)
class DebMetadata:
    """Information extracted from a ``.deb`` file's control stanza."""

    name: str
    version: str
    architecture: str
    description: str
    control: dict[str, str]
    size: int
    md5: str
    sha1: str
    sha256: str

    @property
    def pool_prefix(self) -> str:
        """Return the pool prefix used by Debian repositories.

        ``lib*`` packages get a four-letter prefix (``libf/libfoo``); every
        other package uses the first letter of its name.
        """
        if self.name.startswith("lib"):
            return self.name[:4]
        return self.name[:1]

    @property
    def pool_filename(self) -> str:
        """Return the filename apt expects, e.g. ``foo_1.2.3_amd64.deb``."""
        return f"{self.name}_{self.version}_{self.architecture}.deb"


def parse_deb(path: Path | str) -> DebMetadata:
    """Read control metadata and checksums from a ``.deb`` file on disk.

    Raises ``InvalidDebFileError`` when the archive is unreadable or missing
    required control fields.
    """
    target = Path(path)
    if not target.is_file():
        raise InvalidDebFileError(f"not a file: {target}")

    try:
        with DebFile(str(target)) as deb:
            control = deb.debcontrol()
    except Exception as exc:  # python-debian raises a grab bag of exceptions
        raise InvalidDebFileError(f"failed to parse {target.name}: {exc}") from exc

    for required in ("Package", "Version", "Architecture"):
        if not control.get(required):
            raise InvalidDebFileError(f"missing required control field: {required}")

    raw = target.read_bytes()
    return DebMetadata(
        name=control["Package"].strip(),
        version=control["Version"].strip(),
        architecture=control["Architecture"].strip(),
        description=control.get("Description", "").strip(),
        control=dict(control.items()),
        size=len(raw),
        md5=hashlib.md5(raw).hexdigest(),
        sha1=hashlib.sha1(raw).hexdigest(),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
