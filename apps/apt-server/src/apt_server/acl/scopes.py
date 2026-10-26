# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 scope hierarchy — layer 2 of the access control stack.

Scopes are carried on the PAT / access token and returned by the ``auth``
introspection endpoint. They gate API endpoints (who may upload, delete,
reindex) and — via ``apt:admin`` — provide a global bypass of the DB-level
per-package ACL.

Hierarchy::

    apt:admin          implies apt:write           implies apt:read
    apt:write          implies apt:write:<c>       implies apt:read
    apt:write:<c>      implies apt:read:<c>        implies apt:read
"""

READ = "apt:read"
WRITE = "apt:write"
ADMIN = "apt:admin"

_WRITE_PREFIX = "apt:write:"
_READ_PREFIX = "apt:read:"


def has_admin(scopes: set[str]) -> bool:
    """Return True when ``scopes`` grants unrestricted access."""
    return ADMIN in scopes


def may_read(scopes: set[str]) -> bool:
    """Return True when the caller is at least identified as an apt user."""
    if not scopes:
        return False
    if has_admin(scopes):
        return True
    return READ in scopes or WRITE in scopes or _has_any_prefix(scopes, _READ_PREFIX, _WRITE_PREFIX)


def may_write(scopes: set[str], component: str) -> bool:
    """Return True when the caller may upload or delete in ``component``."""
    if has_admin(scopes):
        return True
    if WRITE in scopes:
        return True
    return (_WRITE_PREFIX + component) in scopes


def may_reindex(scopes: set[str]) -> bool:
    """Return True when the caller may force a global reindex."""
    return has_admin(scopes)


def parse_scopes(raw: str | list[str] | None) -> set[str]:
    """Normalise the ``scope`` field from an introspection response."""
    if not raw:
        return set()
    if isinstance(raw, str):
        return {entry for entry in raw.split() if entry}
    return {entry for entry in raw if entry}


def _has_any_prefix(scopes: set[str], *prefixes: str) -> bool:
    return any(scope.startswith(prefix) for scope in scopes for prefix in prefixes)
