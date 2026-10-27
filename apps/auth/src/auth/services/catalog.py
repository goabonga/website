# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Declarative catalog of the scopes, roles and client grants of a deployment.

The scopes and roles of the services that rely on auth (their names, descriptions and which
role holds which scope) are deployment data, not behaviour of auth. A deployment declares them
in a JSON file; :func:`sync_catalog` makes the database match it, idempotently:

* a scope or a role that is missing is created;
* the description of an existing scope or role is updated when the file gives another one;
* the scopes listed for an existing role are added to it;
* the scopes and grant types listed for an existing OAuth2 client are added to its allowances;
* nothing is ever deleted or removed: what the file no longer lists is left alone.

File format (every key but ``scopes``, ``roles`` and ``clients`` is rejected)::

    {
      "version": 1,
      "scopes": [{"name": "notes:read", "description": "...", "category": "api"}],
      "roles": [{"name": "notes_viewer", "description": "...", "scopes": ["notes:read"]}],
      "clients": [{"client_id": "...", "allowed_scopes": ["notes:read"]}]
    }
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.rbac import ADMIN_SCOPES, DEFAULT_ROLES, Role, RoleScope, Scope
from auth.db.repositories.catalog import CatalogRepository

logger = logging.getLogger(__name__)

SCOPE_NAME = re.compile(r"^[A-Za-z0-9_.*-]+(:[A-Za-z0-9_.*-]+)*$")


class CatalogError(Exception):
    """The catalog cannot be read, is invalid, or does not fit the database."""


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogScope(_Entry):
    """A scope. ``resource`` and ``action`` default to the first and last parts of the name."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    resource: str | None = Field(default=None, min_length=1, max_length=50)
    action: str | None = Field(default=None, min_length=1, max_length=50)
    category: str = Field(default="api", min_length=1, max_length=50)
    is_system: bool = True
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if not SCOPE_NAME.match(value):
            raise ValueError(f"invalid scope name {value!r}")
        return value

    def resolved_resource(self) -> str:
        """The resource: the explicit one, else the part of the name before the first colon."""
        return self.resource or self.name.split(":")[0]

    def resolved_action(self) -> str:
        """The action: the explicit one, else the part of the name after the last colon."""
        if self.action:
            return self.action
        parts = self.name.split(":")
        return parts[-1] if len(parts) > 1 else "*"


class CatalogRole(_Entry):
    """A role and the scopes it holds."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    scopes: list[str] = Field(default_factory=list)
    is_system: bool = True


class CatalogClient(_Entry):
    """Allowances to add to an existing OAuth2 client (it is never created from here)."""

    client_id: str = Field(min_length=1, max_length=64)
    allowed_scopes: list[str] = Field(default_factory=list)
    allowed_grant_types: list[str] = Field(default_factory=list)


class Catalog(_Entry):
    """The whole catalog."""

    version: Literal[1] = 1
    scopes: list[CatalogScope] = Field(default_factory=list)
    roles: list[CatalogRole] = Field(default_factory=list)
    clients: list[CatalogClient] = Field(default_factory=list)

    @classmethod
    def builtin(cls) -> Catalog:
        """The scopes and roles of auth itself (its admin API and console)."""
        return cls(
            scopes=[
                CatalogScope(name=name, description=description, category="admin")
                for name, description in ADMIN_SCOPES.items()
            ],
            roles=[
                CatalogRole(
                    name=name,
                    description=config["description"],
                    scopes=list(config["scopes"]),
                    is_system=bool(config["is_system"]),
                )
                for name, config in DEFAULT_ROLES.items()
            ],
        )

    def check(self) -> None:
        """Reject duplicated names (a name must be declared once)."""
        for kind, names in (
            ("scope", [s.name for s in self.scopes]),
            ("role", [r.name for r in self.roles]),
            ("client", [c.client_id for c in self.clients]),
        ):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            if duplicates:
                raise CatalogError(f"duplicated {kind}: {', '.join(duplicates)}")


def parse_catalog(raw: object) -> Catalog:
    """Validate an already decoded catalog document."""
    try:
        catalog = Catalog.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'catalog'}: {error['msg']}"
            for error in exc.errors()
        )
        raise CatalogError(f"invalid catalog: {problems}") from exc
    catalog.check()
    return catalog


def load_catalog(path: str | Path) -> Catalog:
    """Read and validate the catalog file at ``path``."""
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogError(f"cannot read the catalog {file}: {exc.strerror or exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{file} is not valid JSON: {exc}") from exc
    return parse_catalog(raw)


@dataclass
class SyncReport:
    """What a synchronisation did (or would do, in a dry run)."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """True when at least one row was created or updated."""
        return bool(self.created or self.updated)

    def extend(self, other: SyncReport) -> None:
        """Append the entries of another report."""
        self.created += other.created
        self.updated += other.updated
        self.skipped += other.skipped

    def lines(self, *, dry_run: bool = False) -> list[str]:
        """One human readable line per entry (conditional for a dry run)."""
        create, update, skip = (
            ("would create", "would update", "would skip")
            if dry_run
            else ("created", "updated", "skipped")
        )
        return (
            [f"{create} {item}" for item in self.created]
            + [f"{update} {item}" for item in self.updated]
            + [f"{skip} {item}" for item in self.skipped]
        )

    def to_dict(self) -> dict[str, object]:
        """A JSON serialisable form."""
        return {
            "changed": self.changed,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
        }


async def sync_catalog(
    db: AsyncSession,
    catalog: Catalog,
    repository: CatalogRepository | None = None,
) -> SyncReport:
    """Make the database match ``catalog`` without deleting anything.

    Stages the changes on ``db`` and flushes them; the caller commits (or rolls back for a dry
    run).

    Raises:
        CatalogError: A role lists a scope that neither the catalog nor the database knows. Nothing
            has been written at that point. (Client allowances are not checked: they may hold
            wildcards and the OpenID scopes, which are not rows.)
    """
    repo = repository or CatalogRepository()
    report = SyncReport()
    scopes = await repo.scopes_by_name(db)
    roles = await repo.roles_by_name(db)

    known = set(scopes) | {entry.name for entry in catalog.scopes}
    for role_entry in catalog.roles:
        unknown = sorted(set(role_entry.scopes) - known)
        if unknown:
            raise CatalogError(f"role {role_entry.name} lists unknown scopes: {', '.join(unknown)}")

    for scope_entry in catalog.scopes:
        scope = scopes.get(scope_entry.name)
        if scope is None:
            scope = Scope(
                id=uuid.uuid4(),
                name=scope_entry.name,
                description=scope_entry.description,
                resource=scope_entry.resolved_resource(),
                action=scope_entry.resolved_action(),
                category=scope_entry.category,
                is_system=scope_entry.is_system,
                is_active=scope_entry.is_active,
            )
            await repo.add(db, scope)
            scopes[scope.name] = scope
            report.created.append(f"scope {scope.name}")
        elif scope_entry.description is not None and scope.description != scope_entry.description:
            scope.description = scope_entry.description
            report.updated.append(f"scope {scope.name} (description)")

    for role_entry in catalog.roles:
        role = roles.get(role_entry.name)
        if role is None:
            role = Role(
                id=uuid.uuid4(),
                name=role_entry.name,
                description=role_entry.description,
                is_system=role_entry.is_system,
            )
            await repo.add(db, role)
            roles[role.name] = role
            for scope_name in dict.fromkeys(role_entry.scopes):
                await repo.add(db, RoleScope(role_id=role.id, scope_id=scopes[scope_name].id))
            detail = f" with {len(set(role_entry.scopes))} scope(s)" if role_entry.scopes else ""
            report.created.append(f"role {role.name}{detail}")
            continue
        changes = []
        if role_entry.description is not None and role.description != role_entry.description:
            role.description = role_entry.description
            changes.append("description")
        held = {link.scope.name for link in role.role_scopes if link.scope is not None}
        for scope_name in dict.fromkeys(role_entry.scopes):
            if scope_name not in held:
                await repo.add(db, RoleScope(role_id=role.id, scope_id=scopes[scope_name].id))
                changes.append(f"+{scope_name}")
        if changes:
            report.updated.append(f"role {role.name} ({', '.join(changes)})")

    for client_entry in catalog.clients:
        client = await repo.find_client(db, client_entry.client_id)
        if client is None:
            report.skipped.append(f"client {client_entry.client_id} (not found)")
            continue
        changes = []
        new_scopes = [s for s in client_entry.allowed_scopes if s not in client.allowed_scopes]
        if new_scopes:
            client.allowed_scopes = [*client.allowed_scopes, *dict.fromkeys(new_scopes)]
            changes += [f"+{s}" for s in dict.fromkeys(new_scopes)]
        new_grants = [
            g for g in client_entry.allowed_grant_types if g not in client.allowed_grant_types
        ]
        if new_grants:
            client.allowed_grant_types = [*client.allowed_grant_types, *dict.fromkeys(new_grants)]
            changes += [f"+{g}" for g in dict.fromkeys(new_grants)]
        if changes:
            report.updated.append(f"client {client.client_id} ({', '.join(changes)})")

    await db.flush()
    logger.info(
        "Catalog synchronised: %d created, %d updated, %d skipped",
        len(report.created),
        len(report.updated),
        len(report.skipped),
    )
    return report
