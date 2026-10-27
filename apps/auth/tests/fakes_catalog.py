# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""An in-memory stand-in for CatalogRepository, shared by the catalog and bootstrap tests."""

import uuid
from types import SimpleNamespace

from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.rbac import Role, RoleScope, Scope


class FakeCatalogRepository:
    """Same interface as ``CatalogRepository``, over dictionaries."""

    def __init__(self):
        self.scopes: dict[str, Scope] = {}
        self.roles: dict[str, Role] = {}
        self.clients: dict[str, OAuth2Client] = {}

    async def scopes_by_name(self, db):
        return dict(self.scopes)

    async def roles_by_name(self, db):
        return dict(self.roles)

    async def find_client(self, db, client_id):
        return self.clients.get(client_id)

    async def add(self, db, instance):
        if isinstance(instance, Scope):
            self.scopes[instance.name] = instance
        elif isinstance(instance, Role):
            instance.role_scopes = []
            self.roles[instance.name] = instance
        elif isinstance(instance, RoleScope):
            role = next(r for r in self.roles.values() if r.id == instance.role_id)
            instance.scope = next(s for s in self.scopes.values() if s.id == instance.scope_id)
            role.role_scopes.append(instance)

    def add_scope(self, name, description=None, **kwargs):
        scope = Scope(id=uuid.uuid4(), name=name, description=description, **kwargs)
        self.scopes[name] = scope
        return scope

    def add_role(self, name, description=None, scope_names=()):
        role = Role(id=uuid.uuid4(), name=name, description=description, is_system=True)
        role.role_scopes = [
            RoleScope(role_id=role.id, scope_id=self.scopes[n].id, scope=self.scopes[n])
            for n in scope_names
        ]
        self.roles[name] = role
        return role

    def add_client(self, client_id, scopes=(), grants=()):
        client = SimpleNamespace(
            client_id=client_id, allowed_scopes=list(scopes), allowed_grant_types=list(grants)
        )
        self.clients[client_id] = client
        return client
