# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""HTTP routes consumed by apt clients."""

import base64
import gzip
import subprocess

import pytest
from apt_server.auth.introspection import introspection_client
from apt_server.config import settings
from apt_server.db.models import ACLRole, Package, PackageACL, PackageVisibility
from apt_server.repo import release


def make_package(name, visibility, component="main", owner="alice", acl=()) -> Package:
    package = Package(
        name=name,
        version="1.0",
        architecture="amd64",
        suite="stable",
        component=component,
        owner_id=owner,
        visibility=visibility,
        filename=f"pool/{component}/{name[0]}/{name}/{name}_1.0_amd64.deb",
        size=7,
        md5="0" * 32,
        sha1="1" * 40,
        sha256="2" * 64,
        control={"Package": name, "Version": "1.0", "Architecture": "amd64"},
    )
    package.acl.extend(acl)
    return package


@pytest.fixture(autouse=True)
def repository_settings(monkeypatch: pytest.MonkeyPatch, oidc_settings) -> None:
    monkeypatch.setattr(settings, "apt_components", "main,private")
    monkeypatch.setattr(settings, "apt_public_components", "main")
    monkeypatch.setattr(settings, "apt_architectures", "amd64")
    monkeypatch.setattr(settings, "apt_suites", "stable")
    monkeypatch.setattr(settings, "apt_gpg_key_id", "")
    monkeypatch.setattr(settings, "apt_internal_prefix", "/_internal")


@pytest.fixture
def users(monkeypatch: pytest.MonkeyPatch) -> None:
    """Personal access tokens ``tok-alice`` and ``tok-bob``."""
    claims = {
        "tok-alice": {"sub": "alice", "scope": "apt:read"},
        "tok-bob": {"sub": "bob", "scope": "apt:read", "groups": ["team:ops"]},
    }

    async def validate(token: str) -> dict:
        if token not in claims:
            raise ValueError("unknown token")
        return claims[token]

    monkeypatch.setattr(introspection_client, "validate_opaque_token", validate)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"user:{token}".encode()).decode()}


@pytest.fixture
async def catalog(db):
    db.add_all(
        [
            make_package("tool", PackageVisibility.PUBLIC),
            make_package("draft", PackageVisibility.PRIVATE),
            make_package(
                "shared",
                PackageVisibility.SHARED,
                owner="carol",
                acl=[PackageACL(grantee_group="team:ops", role=ACLRole.READ, granted_by="alice")],
            ),
            make_package("vault", PackageVisibility.PRIVATE, component="private"),
        ]
    )
    await db.commit()


async def test_packages_index_for_anonymous_callers(http, catalog) -> None:
    response = await http.get("/dists/stable/main/binary-amd64/Packages")

    assert response.status_code == 200
    assert "Package: tool\n" in response.text
    assert "draft" not in response.text and "shared" not in response.text


async def test_packages_index_is_filtered_for_the_caller(http, catalog, users) -> None:
    alice = await http.get("/dists/stable/main/binary-amd64/Packages", headers=auth("tok-alice"))
    bob = await http.get("/dists/stable/main/binary-amd64/Packages", headers=auth("tok-bob"))

    assert "Package: draft\n" in alice.text and "Package: shared\n" not in alice.text
    assert "Package: shared\n" in bob.text and "Package: draft\n" not in bob.text


async def test_compressed_packages_index(http, catalog) -> None:
    plain = await http.get("/dists/stable/main/binary-amd64/Packages")
    zipped = await http.get("/dists/stable/main/binary-amd64/Packages.gz")

    assert zipped.status_code == 200
    assert zipped.headers["content-type"] == "application/gzip"
    assert gzip.decompress(zipped.content) == plain.content


async def test_architecture_all_is_accepted(http, catalog) -> None:
    assert (await http.get("/dists/stable/main/binary-all/Packages")).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/dists/nope/main/binary-amd64/Packages",
        "/dists/stable/rogue/binary-amd64/Packages",
        "/dists/stable/main/binary-riscv/Packages",
        "/dists/nope/Release",
    ],
)
async def test_unknown_suite_component_or_architecture_is_not_found(http, catalog, path) -> None:
    assert (await http.get(path)).status_code == 404


async def test_private_component_requires_credentials(http, catalog, users) -> None:
    anonymous = await http.get("/dists/stable/private/binary-amd64/Packages")
    signed_in = await http.get(
        "/dists/stable/private/binary-amd64/Packages", headers=auth("tok-alice")
    )

    assert anonymous.status_code == 401
    assert anonymous.headers["WWW-Authenticate"].startswith("Basic")
    assert signed_in.status_code == 200
    assert "Package: vault\n" in signed_in.text


async def test_bad_credentials_are_rejected(http, catalog, users) -> None:
    response = await http.get("/dists/stable/main/binary-amd64/Packages", headers=auth("wrong"))

    assert response.status_code == 401


async def test_release_for_anonymous_callers(http, catalog) -> None:
    response = await http.get("/dists/stable/Release")

    assert response.status_code == 200
    assert "Components: main\n" in response.text
    assert "main/binary-amd64/Packages.gz" in response.text


async def test_inrelease_equals_release_when_unsigned(http, catalog) -> None:
    inrelease = await http.get("/dists/stable/InRelease")
    plain = await http.get("/dists/stable/Release")

    assert inrelease.status_code == 200
    assert inrelease.text.splitlines()[0] == plain.text.splitlines()[0]
    assert "-----BEGIN PGP" not in inrelease.text


async def test_inrelease_and_detached_signature_are_signed_when_a_key_is_configured(
    http, catalog, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "apt_gpg_key_id", "ABCD")
    monkeypatch.setattr(release, "sign_clearsigned", lambda body: b"CLEARSIGNED")
    monkeypatch.setattr(release, "sign_detached", lambda body: b"DETACHED")

    inrelease = await http.get("/dists/stable/InRelease")
    detached = await http.get("/dists/stable/Release.gpg")

    assert inrelease.content == b"CLEARSIGNED"
    assert detached.content == b"DETACHED"
    assert detached.headers["content-type"] == "application/pgp-signature"


async def test_release_gpg_is_not_found_without_a_key(http, catalog) -> None:
    assert (await http.get("/dists/stable/Release.gpg")).status_code == 404


async def test_pool_download_is_delegated_to_nginx(http, catalog) -> None:
    response = await http.get("/pool/main/t/tool/tool_1.0_amd64.deb")

    assert response.status_code == 200
    assert response.headers["X-Accel-Redirect"] == "/_internal/pool/main/t/tool/tool_1.0_amd64.deb"
    assert response.headers["Content-Type"] == "application/octet-stream"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.content == b""


async def test_pool_prefix_comes_from_settings(http, catalog, monkeypatch) -> None:
    monkeypatch.setattr(settings, "apt_internal_prefix", "/private/")

    response = await http.get("/pool/main/t/tool/tool_1.0_amd64.deb")

    assert response.headers["X-Accel-Redirect"] == "/private/pool/main/t/tool/tool_1.0_amd64.deb"


async def test_private_package_download_is_hidden_from_strangers(http, catalog, users) -> None:
    path = "/pool/main/d/draft/draft_1.0_amd64.deb"

    assert (await http.get(path)).status_code == 404
    assert (await http.get(path, headers=auth("tok-bob"))).status_code == 404
    assert (await http.get(path, headers=auth("tok-alice"))).status_code == 200


async def test_group_grant_allows_download(http, catalog, users) -> None:
    path = "/pool/main/s/shared/shared_1.0_amd64.deb"

    assert (await http.get(path, headers=auth("tok-bob"))).status_code == 200
    assert (await http.get(path, headers=auth("tok-alice"))).status_code == 404


async def test_unknown_pool_file_is_not_found(http, catalog) -> None:
    assert (await http.get("/pool/main/x/nothing/nothing_1.0_amd64.deb")).status_code == 404


async def test_pool_in_private_component_requires_credentials(http, catalog) -> None:
    response = await http.get("/pool/private/v/vault/vault_1.0_amd64.deb")

    assert response.status_code == 401


async def test_pubkey_is_not_found_without_signing_key(http) -> None:
    assert (await http.get("/pubkey.gpg")).status_code == 404


async def test_pubkey_exports_the_configured_key(http, monkeypatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, capture_output, check):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"-----BEGIN PGP PUBLIC KEY BLOCK-----")

    monkeypatch.setattr(settings, "apt_gpg_key_id", "ABCD")
    monkeypatch.setattr(subprocess, "run", fake_run)

    response = await http.get("/pubkey.gpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pgp-keys"
    assert seen == [["/usr/bin/gpg", "--armor", "--export", "ABCD"]]


async def test_pubkey_export_failure_is_not_found(http, monkeypatch) -> None:
    monkeypatch.setattr(settings, "apt_gpg_key_id", "ABCD")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, capture_output, check: subprocess.CompletedProcess(cmd, 2, stdout=b""),
    )

    assert (await http.get("/pubkey.gpg")).status_code == 404
