# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 scope hierarchy of the access control stack."""

import pytest
from apt_server.acl import scopes


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("apt:read apt:write:main", {"apt:read", "apt:write:main"}),
        ("  apt:read   apt:read ", {"apt:read"}),
        (["apt:admin", ""], {"apt:admin"}),
        (None, set()),
        ("", set()),
        ([], set()),
    ],
)
def test_parse_scopes(raw, expected) -> None:
    assert scopes.parse_scopes(raw) == expected


def test_admin_implies_every_scope() -> None:
    admin = {"apt:admin"}

    assert scopes.has_admin(admin)
    assert scopes.may_read(admin)
    assert scopes.may_write(admin, "main")
    assert scopes.may_write(admin, "customer-acme")
    assert scopes.may_reindex(admin)


def test_global_write_covers_every_component_but_not_reindex() -> None:
    write = {"apt:write"}

    assert scopes.may_write(write, "main")
    assert scopes.may_write(write, "customer-acme")
    assert scopes.may_read(write)
    assert not scopes.may_reindex(write)


def test_component_write_is_scoped() -> None:
    ci = {"apt:write:customer-acme"}

    assert scopes.may_write(ci, "customer-acme")
    assert not scopes.may_write(ci, "main")
    assert scopes.may_read(ci)


def test_component_read_scope_identifies_a_reader() -> None:
    assert scopes.may_read({"apt:read:private"})
    assert not scopes.may_write({"apt:read:private"}, "private")


def test_read_without_write() -> None:
    read = {"apt:read"}

    assert scopes.may_read(read)
    assert not scopes.may_write(read, "main")
    assert not scopes.may_reindex(read)


def test_unrelated_scopes_grant_nothing() -> None:
    other = {"openid", "profile", "email"}

    assert not scopes.may_read(other)
    assert not scopes.may_write(other, "main")


def test_empty_scope_set_is_anonymous() -> None:
    assert not scopes.may_read(set())
    assert not scopes.may_write(set(), "main")
    assert not scopes.has_admin(set())
