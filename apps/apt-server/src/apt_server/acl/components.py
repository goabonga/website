# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Component visibility — layer 1 of the access control stack."""

from apt_server.config import settings


def is_known_component(component: str) -> bool:
    """Return True when ``component`` is declared in ``APT_COMPONENTS``."""
    return component in settings.apt_components_list


def is_public_component(component: str) -> bool:
    """Return True when anonymous callers may read ``component``."""
    return component in settings.apt_public_components_list


def known_components() -> list[str]:
    """Return the configured components (read-only view)."""
    return list(settings.apt_components_list)


def public_components() -> list[str]:
    """Return the configured public components (read-only view)."""
    return list(settings.apt_public_components_list)
