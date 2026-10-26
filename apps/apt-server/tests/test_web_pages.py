# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Server-rendered pages: package list, setup guide and package detail."""

import uuid

import pytest
from apt_server.config import settings
from apt_server.db.models import ACLRole, Package, PackageACL, PackageVisibility, UserCache
from apt_server.routes.web import PAGE_SIZE, _keyring_name


def make_package(name, visibility=PackageVisibility.PUBLIC, **extra) -> Package:
    package = Package(
        name=name,
        version=extra.pop("version", "1.0"),
        architecture="amd64",
        suite=extra.pop("suite", "stable"),
        component=extra.pop("component", "main"),
        owner_id=extra.pop("owner_id", "alice"),
        visibility=visibility,
        filename=f"pool/x/{name}/{name}_{uuid.uuid4().hex}.deb",
        size=2048,
        md5="0" * 32,
        sha1="1" * 40,
        sha256="2" * 64,
        description=extra.pop("description", None),
        control={"Package": name},
    )
    package.acl.extend(extra.pop("acl", []))
    return package


@pytest.fixture(autouse=True)
def repository_settings(monkeypatch):
    monkeypatch.setattr(settings, "app_name", "Test Registry")
    monkeypatch.setattr(settings, "apt_components", "main,private")
    monkeypatch.setattr(settings, "apt_public_components", "main")
    monkeypatch.setattr(settings, "apt_suites", "stable,testing")
    monkeypatch.setattr(settings, "oauth2_issuer", "")


@pytest.fixture
async def catalog(db):
    db.add_all(
        [
            make_package("alpha"),
            make_package("beta", suite="testing"),
            make_package("secret", PackageVisibility.PRIVATE, component="private"),
            make_package("mine", PackageVisibility.PRIVATE, owner_id="bob"),
        ]
    )
    await db.commit()


def test_keyring_name_is_derived_from_the_host() -> None:
    assert _keyring_name("apt.example.com") == "apt-example-com"
    assert _keyring_name("localhost:8000") == "localhost-8000"
    assert _keyring_name("") == "apt-server"


async def test_landing_lists_public_packages_for_anonymous_visitors(http, catalog) -> None:
    response = await http.get("/")

    assert response.status_code == 200
    assert "Test Registry" in response.text
    assert "alpha" in response.text and "beta" in response.text
    assert "secret" not in response.text and "mine" not in response.text


async def test_landing_shows_private_packages_to_their_owner(http, catalog, login_caller) -> None:
    login_caller("bob", ["apt:read"], display_name="bob@example.com")

    text = (await http.get("/")).text

    assert "mine" in text and "alpha" in text
    assert "bob@example.com" in text
    assert "/logout" in text


async def test_sign_in_links_appear_when_oauth_is_configured(http, catalog, monkeypatch) -> None:
    monkeypatch.setattr(settings, "oauth2_issuer", "https://issuer.example")

    text = (await http.get("/")).text

    assert 'href="/login"' in text
    assert "Showing public packages only" in text


async def test_landing_has_no_sign_in_without_oauth(http, catalog) -> None:
    assert 'href="/login"' not in (await http.get("/")).text


async def test_landing_filters(http, catalog) -> None:
    by_suite = (await http.get("/", params={"suite": "testing"})).text
    by_name = (await http.get("/", params={"q": "alp"})).text

    assert "beta" in by_suite and "alpha" not in by_suite
    assert "alpha" in by_name and "beta" not in by_name


async def test_component_filter_only_offers_public_components_to_visitors(http, catalog) -> None:
    text = (await http.get("/")).text

    assert '<option value="main"' in text
    assert '<option value="private"' not in text


async def test_empty_state(http) -> None:
    assert "No packages visible" in (await http.get("/")).text


async def test_pagination(http, db) -> None:
    db.add_all([make_package(f"pkg{i:03d}") for i in range(PAGE_SIZE + 5)])
    await db.commit()

    first = (await http.get("/")).text
    second = (await http.get("/", params={"page": 2})).text
    beyond = (await http.get("/", params={"page": 99})).text

    assert "pkg000" in first and "pkg024" in first and "pkg025" not in first
    assert "pkg025" in second and "pkg000" not in second
    assert "pkg029" in beyond
    assert (await http.get("/", params={"page": 0})).status_code == 422


async def test_setup_page_for_visitors(http) -> None:
    response = await http.get("/setup")

    assert response.status_code == 200
    assert "https://test/pubkey.gpg" in response.text
    assert "/etc/apt/keyrings/test.gpg" in response.text
    assert "stable main" in response.text
    assert "Private repository" not in response.text


async def test_setup_page_for_signed_in_users(http, login_caller, monkeypatch) -> None:
    monkeypatch.setattr(settings, "oauth2_issuer", "https://issuer.example/")
    login_caller("bob", [], display_name="bob@example.com")

    text = (await http.get("/setup")).text

    assert "Private repository" in text
    assert "login bob@example.com" in text
    assert "https://issuer.example/auth/settings/tokens" in text


async def test_setup_defaults_to_first_public_component(http, monkeypatch) -> None:
    monkeypatch.setattr(settings, "apt_public_components", "private")

    assert "stable private" in (await http.get("/setup")).text


async def test_package_detail(http, db, catalog) -> None:
    db.add(UserCache(sub="alice", email="alice@example.com"))
    package = make_package("detail", description="A described package")
    db.add(package)
    await db.commit()

    response = await http.get(f"/packages/{package.id}")

    assert response.status_code == 200
    assert "detail" in response.text and "A described package" in response.text
    assert "alice@example.com" in response.text
    assert "sudo apt install detail=1.0" in response.text


async def test_private_package_detail_is_hidden(http, db, login_caller) -> None:
    package = make_package("hidden", PackageVisibility.PRIVATE, owner_id="bob")
    db.add(package)
    await db.commit()

    assert (await http.get(f"/packages/{package.id}")).status_code == 404
    login_caller("carol", [])
    assert (await http.get(f"/packages/{package.id}")).status_code == 404
    login_caller("bob", [])
    assert (await http.get(f"/packages/{package.id}")).status_code == 200


async def test_granted_user_can_view_a_shared_package(http, db, login_caller) -> None:
    package = make_package(
        "shared",
        PackageVisibility.SHARED,
        acl=[PackageACL(grantee_user_id="carol", role=ACLRole.READ, granted_by="alice")],
    )
    db.add(package)
    await db.commit()
    login_caller("carol", [])

    assert (await http.get(f"/packages/{package.id}")).status_code == 200


async def test_unknown_package_is_not_found(http) -> None:
    assert (await http.get(f"/packages/{uuid.uuid4()}")).status_code == 404
    assert (await http.get("/packages/not-a-uuid")).status_code == 422


async def test_the_sidebar_is_a_navigation_landmark(http) -> None:
    text = (await http.get("/")).text

    assert '<nav class="admin-sidebar" aria-label="Main">' in text
