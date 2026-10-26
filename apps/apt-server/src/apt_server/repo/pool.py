# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pool storage: where the actual ``.deb`` bytes live on disk.

Layout follows the standard Debian pool convention::

    <APT_REPO_ROOT>/pool/<component>/<prefix>/<name>/<name>_<version>_<arch>.deb

Where ``<prefix>`` is ``libX/libXname`` for ``libfoo``-style packages and the
first letter of the package name otherwise. The relative pool path (everything
after ``<APT_REPO_ROOT>/``) is stored in ``packages.filename`` and passed to
nginx in the ``X-Accel-Redirect`` header at download time.
"""

from pathlib import Path

from apt_server.config import settings
from apt_server.repo.debfile import DebMetadata


def repo_root() -> Path:
    """Return the filesystem root used for pool/ and dists/ storage."""
    return Path(settings.apt_repo_root)


def pool_relative_path(metadata: DebMetadata, component: str) -> str:
    """Return the pool-relative path (no leading slash) for a package."""
    return f"pool/{component}/{metadata.pool_prefix}/{metadata.name}/{metadata.pool_filename}"


def pool_absolute_path(metadata: DebMetadata, component: str) -> Path:
    """Return the absolute on-disk path for a package's pool location."""
    return repo_root() / pool_relative_path(metadata, component)


def ensure_pool_dir(path: Path) -> None:
    """Create the parent directories for a pool path if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_deb(source: Path | str, metadata: DebMetadata, component: str) -> Path:
    """Move a staged ``.deb`` into the pool, returning its final path.

    The caller is expected to have already written the upload to ``source``
    (for example, FastAPI's ``UploadFile`` saved to a tmp file) and to have
    validated ``metadata`` against ``APT_COMPONENTS``. If a file already
    exists at the destination with the same SHA-256 we keep it in place;
    mismatched content raises ``FileExistsError`` so the API can return
    ``409 Conflict`` without silently clobbering.
    """
    source_path = Path(source)
    destination = pool_absolute_path(metadata, component)
    ensure_pool_dir(destination)

    if destination.exists():
        existing_sha256 = _sha256(destination)
        if existing_sha256 == metadata.sha256:
            if source_path.resolve() != destination.resolve():
                source_path.unlink(missing_ok=True)
            return destination
        raise FileExistsError(
            f"pool collision for {metadata.pool_filename}: "
            f"existing sha256={existing_sha256} new sha256={metadata.sha256}"
        )

    import shutil

    shutil.move(str(source_path), str(destination))
    return destination


def delete_deb(relative_path: str) -> None:
    """Remove a pool file referenced by its pool-relative path."""
    absolute = repo_root() / relative_path
    absolute.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
