# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Per-package ACL check — layer 3 of the access control stack.

Every read (pool download, Packages index, JSON listing) and every write
(PATCH, DELETE, ACL mutation) funnels through :func:`visible_package_filter`
or :func:`can_read`/`can_write`. The caller carries its OIDC ``sub``, the
scopes parsed from introspection, and the groups claim when present.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, or_, select

from apt_server.acl import scopes as scope_rules
from apt_server.db.models import Package, PackageACL, PackageVisibility


@dataclass(slots=True, frozen=True)
class Caller:
    """Identity and entitlements resolved from a bearer or basic-auth credential."""

    sub: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    groups: frozenset[str] = field(default_factory=frozenset)
    display_name: str = ""  # email
    name: str = ""  # human-readable name
    avatar_url: str = ""
    is_session: bool = False

    @property
    def is_admin(self) -> bool:
        return scope_rules.has_admin(set(self.scopes))


def visible_package_filter(caller: Caller | None) -> ColumnElement[bool]:
    """Return a SQLAlchemy boolean expression scoping rows to the caller.

    - Anonymous callers see only ``visibility = 'public'`` packages.
    - Admins see everything.
    - Authenticated callers see public packages + their own + any package
      granted to them via ``package_acl`` (user or group grantee).
    """
    public_only = Package.visibility == PackageVisibility.PUBLIC
    if caller is None:
        return public_only

    if caller.is_admin:
        return _always_true()

    owner_match = Package.owner_id == caller.sub
    # Match ACL by sub OR by display_name (email) — grantees are often
    # entered as emails but caller.sub is a pairwise UUID.
    user_identifiers = [caller.sub]
    if caller.display_name and caller.display_name != caller.sub:
        user_identifiers.append(caller.display_name)
    user_grant = select(PackageACL.package_id).where(
        PackageACL.package_id == Package.id,
        PackageACL.grantee_user_id.in_(user_identifiers),
    )
    group_clauses: list[ColumnElement[bool]] = []
    if caller.groups:
        group_clauses.append(
            Package.id.in_(
                select(PackageACL.package_id).where(
                    PackageACL.grantee_group.in_(caller.groups),
                )
            )
        )

    return or_(
        public_only,
        owner_match,
        Package.id.in_(user_grant),
        *group_clauses,
    )


def can_read(caller: Caller | None, package: Package) -> bool:
    """Return True when the caller may read a specific package.

    Mirrors :func:`visible_package_filter` but applied to a single in-memory
    ``Package`` row (typically loaded with its ``acl`` relationship).
    """
    if package.visibility == PackageVisibility.PUBLIC:
        return True
    if caller is None:
        return False
    if caller.is_admin:
        return True
    if package.owner_id == caller.sub:
        return True
    return _has_matching_acl(caller, package.acl, roles=("read", "write"))


def can_write(caller: Caller | None, package: Package) -> bool:
    """Return True when the caller may modify a specific package.

    Write access requires ownership, ``apt:admin``, or an explicit ``write``
    grant in ``package_acl``.
    """
    if caller is None:
        return False
    if caller.is_admin:
        return True
    if package.owner_id == caller.sub:
        return True
    return _has_matching_acl(caller, package.acl, roles=("write",))


def _has_matching_acl(
    caller: Caller,
    acl_rows: Iterable[PackageACL],
    *,
    roles: tuple[str, ...],
) -> bool:
    for row in acl_rows:
        if row.role.value not in roles:
            continue
        if row.grantee_user_id and (
            row.grantee_user_id == caller.sub
            or (caller.display_name and row.grantee_user_id == caller.display_name)
        ):
            return True
        if row.grantee_group and row.grantee_group in caller.groups:
            return True
    return False


def _always_true() -> ColumnElement[bool]:
    """SQLAlchemy expression equivalent to ``TRUE``."""
    return Package.id == Package.id
