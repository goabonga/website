# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""``Packages`` and ``Release`` rendering from package rows."""

import gzip
import hashlib
import subprocess
import uuid
from datetime import UTC, datetime

import pytest
from apt_server.config import settings
from apt_server.db.models import Package, PackageVisibility
from apt_server.repo import indexes, release


def make_package(**overrides) -> Package:
    values = {
        "id": uuid.uuid4(),
        "name": "demo",
        "version": "1.2.3",
        "architecture": "amd64",
        "suite": "stable",
        "component": "main",
        "owner_id": "alice",
        "visibility": PackageVisibility.PUBLIC,
        "filename": "pool/main/d/demo/demo_1.2.3_amd64.deb",
        "size": 1234,
        "md5": "0" * 32,
        "sha1": "1" * 40,
        "sha256": "2" * 64,
        "description": "demo package",
        "control": {
            "Package": "demo",
            "Version": "1.2.3",
            "Architecture": "amd64",
            "Maintainer": "Chris",
            "Description": "demo package",
        },
        "uploaded_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Package(**values)


def test_stanza_starts_with_the_preferred_field_order() -> None:
    stanza = indexes.render_stanza(make_package())

    lines = stanza.splitlines()
    assert lines[:3] == ["Package: demo", "Version: 1.2.3", "Architecture: amd64"]
    assert lines.index("Maintainer: Chris") < lines.index("Description: demo package")
    assert stanza.endswith("\n")


def test_stanza_ends_with_repository_computed_headers() -> None:
    stanza = indexes.render_stanza(make_package())

    assert stanza.splitlines()[-5:] == [
        "Filename: pool/main/d/demo/demo_1.2.3_amd64.deb",
        "Size: 1234",
        "MD5sum: " + "0" * 32,
        "SHA1: " + "1" * 40,
        "SHA256: " + "2" * 64,
    ]


def test_stanza_appends_unknown_fields_alphabetically_and_skips_reserved_ones() -> None:
    control = {
        "Package": "demo",
        "Zeta": "z",
        "Alpha": "a",
        "Filename": "ignored",
        "Size": "999",
        "SHA256": "bad",
    }

    stanza = indexes.render_stanza(make_package(control=control))

    assert stanza.index("Alpha: a") < stanza.index("Zeta: z")
    assert "ignored" not in stanza
    assert "Size: 999" not in stanza
    assert "SHA256: bad" not in stanza


def test_packages_file_separates_stanzas_with_a_blank_line() -> None:
    first = make_package(version="1.0.0")
    second = make_package(version="2.0.0")

    text = indexes.render_packages_file([first, second]).decode()

    assert text.startswith("Package: demo\n")
    assert text.count("\n\nPackage: demo\n") == 1


def test_empty_packages_file_is_empty() -> None:
    assert indexes.render_packages_file([]) == b""


def test_gzip_is_deterministic_and_reversible() -> None:
    body = indexes.render_packages_file([make_package()])

    assert indexes.gzip_packages(body) == indexes.gzip_packages(body)
    assert gzip.decompress(indexes.gzip_packages(body)) == body


def test_index_checksum() -> None:
    body = b"hello"

    checksum = release.index_checksum("main/binary-amd64/Packages", body)

    assert checksum.size == 5
    assert checksum.sha256 == hashlib.sha256(body).hexdigest()
    assert checksum.md5 == hashlib.md5(body).hexdigest()
    assert checksum.sha1 == hashlib.sha1(body).hexdigest()


def test_release_lists_header_and_every_index() -> None:
    body = indexes.render_packages_file([make_package()])

    text = release.render_release(
        suite="stable",
        components=["main", "private"],
        architectures=["amd64", "arm64"],
        indexes={
            "main/binary-amd64/Packages.gz": indexes.gzip_packages(body),
            "main/binary-amd64/Packages": body,
        },
    ).decode()

    assert "Origin: apt-server" in text
    assert "Label: apt-server" in text
    assert "Suite: stable" in text
    assert "Codename: stable" in text
    assert "Architectures: amd64 arm64" in text
    assert "Components: main private" in text
    for section in ("MD5Sum:", "SHA1:", "SHA256:"):
        assert section in text
    # entries are sorted by path
    assert text.index("main/binary-amd64/Packages\n") < text.index("main/binary-amd64/Packages.gz")
    assert f" {hashlib.sha256(body).hexdigest()} {len(body):>16} main/binary-amd64/Packages" in text


def test_release_uses_configured_origin_and_label(monkeypatch) -> None:
    monkeypatch.setattr(settings, "apt_origin", "acme")
    monkeypatch.setattr(settings, "apt_label", "acme-label")

    text = release.render_release(
        suite="stable", components=["main"], architectures=["amd64"], indexes={}
    ).decode()

    assert "Origin: acme\n" in text
    assert "Label: acme-label\n" in text


def test_signing_is_a_noop_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "apt_gpg_key_id", "")

    assert release.sign_clearsigned(b"Release\n") == b"Release\n"
    assert release.sign_detached(b"Release\n") == b""


def test_signing_delegates_to_gpg(monkeypatch) -> None:
    calls: list[tuple[list[str], bytes]] = []

    def fake_run(cmd, input, capture_output, check):
        calls.append((cmd, input))
        return subprocess.CompletedProcess(cmd, 0, stdout=b"SIGNED", stderr=b"")

    monkeypatch.setattr(settings, "apt_gpg_key_id", "ABCD1234")
    monkeypatch.setattr(release.subprocess, "run", fake_run)

    assert release.sign_clearsigned(b"body") == b"SIGNED"
    assert release.sign_detached(b"body") == b"SIGNED"

    clearsign, detached = (cmd for cmd, _ in calls)
    assert "--clearsign" in clearsign and "ABCD1234" in clearsign
    assert "--detach-sign" in detached and "--armor" in detached
    assert all(body == b"body" for _, body in calls)
    assert "--batch" in clearsign and "loopback" in clearsign


def test_gpg_failure_propagates(monkeypatch) -> None:
    def fake_run(cmd, input, capture_output, check):
        raise subprocess.CalledProcessError(2, cmd)

    monkeypatch.setattr(settings, "apt_gpg_key_id", "ABCD1234")
    monkeypatch.setattr(release.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        release.sign_clearsigned(b"body")
