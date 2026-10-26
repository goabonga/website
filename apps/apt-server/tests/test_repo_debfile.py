# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Parsing of uploaded ``.deb`` files."""

import hashlib

import pytest
from apt_server.repo.debfile import DebMetadata, InvalidDebFileError, parse_deb
from debfactory import build_deb


def write(tmp_path, content: bytes, name: str = "pkg.deb"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_parse_reads_control_fields_and_checksums(tmp_path) -> None:
    raw = build_deb("demo", "1.2.3", "amd64", "a demo", {"Depends": "libc6"})

    meta = parse_deb(write(tmp_path, raw))

    assert (meta.name, meta.version, meta.architecture) == ("demo", "1.2.3", "amd64")
    assert meta.description == "a demo"
    assert meta.control["Depends"] == "libc6"
    assert meta.size == len(raw)
    assert meta.md5 == hashlib.md5(raw).hexdigest()
    assert meta.sha1 == hashlib.sha1(raw).hexdigest()
    assert meta.sha256 == hashlib.sha256(raw).hexdigest()


def test_parse_accepts_a_string_path(tmp_path) -> None:
    path = write(tmp_path, build_deb())

    assert parse_deb(str(path)).name == "demo"


def test_parse_rejects_a_missing_file(tmp_path) -> None:
    with pytest.raises(InvalidDebFileError, match="not a file"):
        parse_deb(tmp_path / "missing.deb")


def test_parse_rejects_a_file_that_is_not_a_deb(tmp_path) -> None:
    with pytest.raises(InvalidDebFileError, match="failed to parse"):
        parse_deb(write(tmp_path, b"not an archive"))


@pytest.mark.parametrize("field", ["Package", "Version", "Architecture"])
def test_parse_requires_core_control_fields(tmp_path, field) -> None:
    raw = build_deb(extra_control={field: ""})

    with pytest.raises(InvalidDebFileError, match=field):
        parse_deb(write(tmp_path, raw))


def metadata(name: str) -> DebMetadata:
    return DebMetadata(name, "1.0", "amd64", "", {}, 1, "", "", "")


def test_pool_prefix_is_first_letter_or_four_letters_for_lib_packages() -> None:
    assert metadata("curl").pool_prefix == "c"
    assert metadata("libfoo").pool_prefix == "libf"
    assert metadata("lib").pool_prefix == "lib"


def test_pool_filename_follows_the_debian_convention() -> None:
    assert metadata("demo").pool_filename == "demo_1.0_amd64.deb"
