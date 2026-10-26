# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Component visibility, the first layer of the access control stack."""

import pytest
from apt_server.acl import components
from apt_server.config import Settings, settings


@pytest.fixture(autouse=True)
def configured_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "apt_components", "main,contrib,customer-acme")
    monkeypatch.setattr(settings, "apt_public_components", "main,contrib")


def test_public_components_are_known() -> None:
    assert components.is_known_component("main")
    assert components.is_public_component("main")


def test_private_components_are_known_but_not_public() -> None:
    assert components.is_known_component("customer-acme")
    assert not components.is_public_component("customer-acme")


def test_unknown_components_are_rejected() -> None:
    assert not components.is_known_component("rogue")
    assert not components.is_public_component("rogue")


def test_list_accessors_return_copies() -> None:
    known = components.known_components()
    public = components.public_components()

    known.append("mutated")
    public.append("mutated")

    assert components.known_components() == ["main", "contrib", "customer-acme"]
    assert components.public_components() == ["main", "contrib"]


def test_settings_split_and_trim_comma_separated_lists() -> None:
    cfg = Settings(_env_file=None, apt_components=" main , private ,, ", apt_public_components="")

    assert cfg.apt_components_list == ["main", "private"]
    assert cfg.apt_public_components_list == []


def test_defaults_serve_a_single_public_main_component() -> None:
    cfg = Settings(_env_file=None)

    assert cfg.apt_components_list == ["main"]
    assert cfg.apt_public_components_list == ["main"]
