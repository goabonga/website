# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the ownership and default-resolution rules of custom_domain/routes/domains.py."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.auth import AuthContext
from custom_domain.auth.models import User
from custom_domain.config import settings
from custom_domain.models.enums import DomainStatus
from custom_domain.routes.domains import create_domain, lookup_domain, update_domain
from custom_domain.schemas.domain import DomainCreate, DomainUpdate
from fastapi import HTTPException


def auth_for(client_id="tenant-a", scopes=("custom-domain:write", "custom-domain:lookup")):
    return AuthContext(user=User(id=uuid4(), scopes=list(scopes), client_id=client_id))


def db_returning(value):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    db.execute = AsyncMock(return_value=result)
    db.scalar = AsyncMock(return_value=0)
    return db


def active_domain(client_id="tenant-a"):
    domain = MagicMock()
    domain.domain = "shop.example.com"
    domain.owner_id = "org_1"
    domain.owner_type = "organization"
    domain.client_id = client_id
    domain.status = DomainStatus.ACTIVE
    domain.metadata_ = {}
    return domain


class TestLookupScope:
    """/domains/lookup/{name} only reveals the caller's own domains."""

    @staticmethod
    async def run(auth, found):
        db = db_returning(found)
        try:
            return await lookup_domain("Shop.Example.com", db, auth), db
        except HTTPException as error:
            return error, db

    @staticmethod
    def compiled(db):
        return str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))

    @pytest.mark.asyncio
    async def test_query_is_restricted_to_the_callers_client(self):
        result, db = await self.run(auth_for("tenant-a"), active_domain())
        assert result.domain == "shop.example.com"
        sql = self.compiled(db)
        assert "custom_domains.client_id = 'tenant-a'" in sql
        assert "custom_domains.domain = 'shop.example.com'" in sql
        assert "custom_domains.status = 'active'" in sql

    @pytest.mark.asyncio
    async def test_another_clients_domain_is_not_found(self):
        result, _ = await self.run(auth_for("tenant-b"), None)
        assert isinstance(result, HTTPException)
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_administrator_is_not_restricted(self):
        admin = auth_for(None, scopes=("custom-domain:admin", "custom-domain:lookup"))
        result, db = await self.run(admin, active_domain("tenant-z"))
        assert result.client_id == "tenant-z"
        assert "client_id =" not in self.compiled(db)

    @pytest.mark.asyncio
    async def test_the_administration_scope_is_configurable(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_scope", "ops:root")
        _, db = await self.run(auth_for(None, scopes=("ops:root",)), active_domain())
        assert "client_id =" not in self.compiled(db)
        _, db = await self.run(
            auth_for("tenant-a", scopes=("custom-domain:admin", "custom-domain:lookup")),
            active_domain(),
        )
        assert "custom_domains.client_id = 'tenant-a'" in self.compiled(db)


class TestTargetResolution:
    """Upstream and CNAME targets come from the request, the client, then the settings."""

    @staticmethod
    def client(upstream="/run/app.sock", cname="apps.client.example"):
        client = MagicMock()
        client.max_domains = None
        client.default_upstream_target = upstream
        client.default_cname_target = cname
        return client

    async def create(self, client, data=None):
        db = db_returning(None)

        async def refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)

        db.refresh = refresh
        db.add = MagicMock()
        data = data or DomainCreate(domain="shop.example.com", owner_id="org_1")
        with (
            patch("custom_domain.routes.domains.domain_service") as service,
            patch("custom_domain.tasks.verify_domain_dns"),
        ):
            service.validate_domain_name.return_value = (True, None)
            service.get_authorized_client = AsyncMock(return_value=client)
            response = await create_domain(data, db, auth_for())
        return response, db.add.call_args.args[0]

    @pytest.mark.asyncio
    async def test_client_defaults_are_used(self):
        response, domain = await self.create(self.client())
        assert domain.upstream_target == "/run/app.sock"
        assert domain.cname_target == "apps.client.example"
        assert response.cname_target == "apps.client.example"
        assert "apps.client.example" in response.dns_instructions

    @pytest.mark.asyncio
    async def test_request_values_win(self):
        data = DomainCreate(
            domain="shop.example.com",
            owner_id="org_1",
            upstream_target="/run/other.sock",
            cname_target="edge.example.net",
        )
        _, domain = await self.create(self.client(), data)
        assert domain.upstream_target == "/run/other.sock"
        assert domain.cname_target == "edge.example.net"

    @pytest.mark.asyncio
    async def test_setting_is_the_last_resort_for_the_cname(self, monkeypatch):
        monkeypatch.setattr(settings, "default_cname_target", "fallback.example.net")
        _, domain = await self.create(self.client(cname=None))
        assert domain.cname_target == "fallback.example.net"

    @pytest.mark.asyncio
    async def test_no_cname_anywhere_is_a_client_error(self, monkeypatch):
        monkeypatch.setattr(settings, "default_cname_target", "")
        with pytest.raises(HTTPException) as exc:
            await self.create(self.client(cname=None))
        assert exc.value.status_code == 400
        assert "CNAME" in exc.value.detail

    @pytest.mark.asyncio
    async def test_no_upstream_anywhere_is_a_client_error(self):
        with pytest.raises(HTTPException) as exc:
            await self.create(self.client(upstream=None))
        assert exc.value.status_code == 400
        assert "upstream" in exc.value.detail


class TestUpdateWhileDeprovisioning:
    """A domain that is being deleted can not be modified."""

    @pytest.mark.asyncio
    async def test_update_is_refused(self):
        domain = active_domain()
        domain.status = DomainStatus.DEPROVISIONING
        with pytest.raises(HTTPException) as exc:
            await update_domain(
                uuid4(), DomainUpdate(metadata={"a": 1}), db_returning(domain), auth_for()
            )
        assert exc.value.status_code == 409
