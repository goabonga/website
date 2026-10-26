# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the per-client ownership of nginx templates."""

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from alembic import command
from custom_domain.auth import AuthContext
from custom_domain.auth.models import User
from custom_domain.models import NginxTemplate
from custom_domain.models.enums import DomainStatus
from custom_domain.routes.admin.clients import create_client, update_client
from custom_domain.routes.admin.templates import (
    create_template,
    list_templates,
    set_default_template,
)
from custom_domain.routes.domains import create_domain, update_domain
from custom_domain.routes.templates import list_available_templates
from custom_domain.schemas import ClientCreate, ClientUpdate, TemplateCreate
from custom_domain.schemas.domain import DomainCreate, DomainUpdate
from custom_domain.services.template import template_service
from custom_domain.tasks.provisioning import resolve_template
from fastapi import HTTPException

from tests.test_migrations import _config
from tests.test_routes_access import deactivated_client  # noqa: F401 - fixture


def compiled(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


def auth_for(client_id="tenant-a", scopes=("custom-domain:read", "custom-domain:write")):
    return AuthContext(user=User(id=uuid4(), scopes=list(scopes), client_id=client_id))


def admin_auth():
    return AuthContext(
        user=User(
            id=uuid4(),
            scopes=["custom-domain:admin", "custom-domain:admin:templates"],
            client_id="ops",
        )
    )


def db_returning(*values):
    db = AsyncMock()
    results = []
    for value in values:
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        results.append(result)
    db.execute = AsyncMock(side_effect=results)
    db.scalar = AsyncMock(return_value=0)
    db.add = MagicMock()
    return db


class TestModelAndMigration:
    """The owner is stored on the template."""

    def test_template_has_an_optional_client_id(self):
        column = NginxTemplate.__table__.c.client_id
        assert column.nullable is True
        assert column.index is True
        assert NginxTemplate(slug="s", name="n").client_id is None

    def test_migration_adds_and_removes_the_column(self):
        buffer = io.StringIO()
        command.upgrade(_config(buffer), "001_initial:002_template_owner", sql=True)
        sql = buffer.getvalue()
        assert "ALTER TABLE nginx_templates ADD COLUMN client_id VARCHAR(255)" in sql
        assert "CREATE INDEX ix_nginx_templates_client_id ON nginx_templates (client_id)" in sql

        buffer = io.StringIO()
        command.downgrade(_config(buffer), "002_template_owner:001_initial", sql=True)
        assert "DROP COLUMN client_id" in buffer.getvalue()


class TestGetUsableTemplate:
    """A client may use shared templates and its own, never another client's."""

    @pytest.mark.asyncio
    async def test_query_allows_shared_and_owned_templates(self):
        db = db_returning(MagicMock())
        await template_service.get_usable_template(db, 7, "tenant-a")
        sql = compiled(db.execute.await_args.args[0])
        assert "nginx_templates.id = 7" in sql
        assert "nginx_templates.is_active IS true" in sql
        assert "nginx_templates.client_id IS NULL OR nginx_templates.client_id = 'tenant-a'" in sql

    @pytest.mark.asyncio
    async def test_unknown_template_is_none(self):
        assert await template_service.get_usable_template(db_returning(None), 7, "t") is None


class TestDomainRoutes:
    """Domains can only reference templates their client may use."""

    @pytest.mark.asyncio
    async def test_create_refuses_a_template_of_another_client(self):
        client = MagicMock(max_domains=None, default_upstream_target="/run/a.sock")
        client.default_cname_target = "apps.example.com"
        data = DomainCreate(domain="shop.example.com", owner_id="o", nginx_template_id=9)
        db = db_returning(None)
        with (
            patch("custom_domain.routes.domains.domain_service") as service,
            patch("custom_domain.routes.domains.template_service") as templates,
            patch("custom_domain.tasks.verify_domain_dns"),
        ):
            service.validate_domain_name.return_value = (True, None)
            service.get_authorized_client = AsyncMock(return_value=client)
            templates.get_usable_template = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await create_domain(data, db, auth_for())
        assert exc.value.status_code == 400
        assert "not available" in exc.value.detail
        assert templates.get_usable_template.await_args.args[1:] == (9, "tenant-a")
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_accepts_a_usable_template(self):
        client = MagicMock(max_domains=None, default_upstream_target="/run/a.sock")
        client.default_cname_target = "apps.example.com"
        data = DomainCreate(domain="shop.example.com", owner_id="o", nginx_template_id=9)
        db = db_returning(None)

        async def refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)

        db.refresh = refresh
        with (
            patch("custom_domain.routes.domains.domain_service") as service,
            patch("custom_domain.routes.domains.template_service") as templates,
            patch("custom_domain.tasks.verify_domain_dns"),
        ):
            service.validate_domain_name.return_value = (True, None)
            service.get_authorized_client = AsyncMock(return_value=client)
            templates.get_usable_template = AsyncMock(return_value=MagicMock())
            await create_domain(data, db, auth_for())
        assert db.add.call_args.args[0].nginx_template_id == 9

    @pytest.mark.asyncio
    async def test_update_checks_against_the_domains_client_even_for_an_admin(self):
        domain = MagicMock(client_id="tenant-a", status=DomainStatus.ACTIVE)
        db = db_returning(domain)
        with patch("custom_domain.routes.domains.template_service") as templates:
            templates.get_usable_template = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await update_domain(uuid4(), DomainUpdate(nginx_template_id=4), db, admin_auth())
        assert exc.value.status_code == 400
        assert templates.get_usable_template.await_args.args[1:] == (4, "tenant-a")

    @pytest.mark.asyncio
    async def test_update_without_a_template_does_not_check(self):
        domain = MagicMock(client_id="tenant-a", status=DomainStatus.ACTIVE)
        db = db_returning(domain)
        with (
            patch("custom_domain.routes.domains.template_service") as templates,
            patch("custom_domain.routes.domains.DomainResponse"),
        ):
            templates.get_usable_template = AsyncMock()
            await update_domain(uuid4(), DomainUpdate(metadata={"a": 1}), db, auth_for())
        templates.get_usable_template.assert_not_awaited()


class TestAdminTemplateRoutes:
    """Administrators create client-owned templates and keep the default shared."""

    @pytest.mark.asyncio
    async def test_create_stores_the_owner(self):
        data = TemplateCreate(
            slug="branded",
            name="Branded",
            http_template="server {}",
            https_template="server {}",
            client_id="tenant-a",
        )
        db = db_returning(None)

        async def refresh(obj):
            obj.id = 3
            obj.created_at = obj.updated_at = datetime.now(UTC)

        db.refresh = refresh
        result = await create_template(data, db, admin_auth())
        assert db.add.call_args.args[0].client_id == "tenant-a"
        assert result.client_id == "tenant-a"

    @pytest.mark.asyncio
    async def test_create_without_owner_is_shared(self):
        data = TemplateCreate(slug="common", name="Common", http_template="x", https_template="y")
        db = db_returning(None)

        async def refresh(obj):
            obj.id = 4
            obj.created_at = obj.updated_at = datetime.now(UTC)

        db.refresh = refresh
        result = await create_template(data, db, admin_auth())
        assert db.add.call_args.args[0].client_id is None
        assert result.client_id is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kwargs", "expected", "unexpected"),
        [
            ({"client_id": "tenant-a"}, "nginx_templates.client_id = 'tenant-a'", "IS NULL"),
            ({"shared": True}, "nginx_templates.client_id IS NULL", "IS NOT NULL"),
            ({"shared": False}, "nginx_templates.client_id IS NOT NULL", "client_id IS NULL"),
            ({}, "ORDER BY nginx_templates.name", "WHERE"),
        ],
    )
    async def test_list_filters(self, kwargs, expected, unexpected):
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)
        await list_templates(db, admin_auth(), **kwargs)
        sql = compiled(db.execute.await_args.args[0])
        assert expected in sql
        assert unexpected not in sql

    @pytest.mark.asyncio
    async def test_client_owned_template_can_not_be_the_default(self):
        template = MagicMock(client_id="tenant-a", is_default=False)
        db = db_returning(template)
        with pytest.raises(HTTPException) as exc:
            await set_default_template(1, db, admin_auth())
        assert exc.value.status_code == 400
        assert "global default" in exc.value.detail
        assert template.is_default is False


class TestClientDefaultTemplate:
    """A client's default template must be usable by that client."""

    @pytest.mark.asyncio
    async def test_create_refuses_a_foreign_default(self):
        data = ClientCreate(
            client_id="tenant-a",
            name="A",
            default_upstream_target="/run/a.sock",
            default_cname_target="apps.example.com",
            default_nginx_template_id=5,
        )
        db = db_returning(None)
        with patch("custom_domain.routes.admin.clients.template_service") as templates:
            templates.get_usable_template = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await create_client(data, db, admin_auth())
        assert exc.value.status_code == 400
        assert templates.get_usable_template.await_args.args[1:] == (5, "tenant-a")
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_checks_the_new_default(self):
        client = MagicMock(client_id="tenant-a")
        db = db_returning(client)
        with patch("custom_domain.routes.admin.clients.template_service") as templates:
            templates.get_usable_template = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await update_client(1, ClientUpdate(default_nginx_template_id=8), db, admin_auth())
        assert exc.value.status_code == 400
        assert templates.get_usable_template.await_args.args[1:] == (8, "tenant-a")

    @pytest.mark.asyncio
    async def test_update_without_a_template_does_not_check(self):
        client = MagicMock(client_id="tenant-a")
        db = db_returning(client)
        db.refresh = AsyncMock()
        with patch("custom_domain.routes.admin.clients.template_service") as templates:
            templates.get_usable_template = AsyncMock()
            with patch("custom_domain.routes.admin.clients.ClientResponse") as response:
                await update_client(1, ClientUpdate(name="New"), db, admin_auth())
        templates.get_usable_template.assert_not_awaited()
        response.model_validate.assert_called_once()


class TestAvailableTemplates:
    """GET /templates: what a client can choose, without the sources."""

    @staticmethod
    def templates():
        shared = MagicMock(id=1, slug="default", name="Default", description=None, client_id=None)
        owned = MagicMock(id=2, slug="branded", name="Branded", description="d", client_id="a")
        for template, name in ((shared, "Default"), (owned, "Branded")):
            template.name = name
        return [shared, owned]

    async def run(self, auth):
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = self.templates()
        db.execute = AsyncMock(return_value=result)
        return await list_available_templates(db, auth), db

    @pytest.mark.asyncio
    async def test_client_sees_shared_and_own_templates(self):
        response, db = await self.run(auth_for())
        sql = compiled(db.execute.await_args.args[0])
        assert "nginx_templates.is_active IS true" in sql
        assert "client_id IS NULL OR nginx_templates.client_id = 'tenant-a'" in sql
        assert [(t.slug, t.shared) for t in response.items] == [
            ("default", True),
            ("branded", False),
        ]
        assert response.total == 2
        assert not hasattr(response.items[0], "http_template")

    @pytest.mark.asyncio
    async def test_administrator_sees_every_active_template(self):
        _, db = await self.run(admin_auth())
        assert (
            "client_id"
            not in compiled(db.execute.await_args.args[0])
            .split("ORDER BY")[0]
            .replace("nginx_templates.client_id,", "")
            .split("WHERE")[-1]
        )


class TestProvisioningResolution:
    """The provisioning task never uses another client's template."""

    @staticmethod
    def session(*values):
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.side_effect = list(values)
        return session

    @staticmethod
    def domain(template_id=None):
        return MagicMock(nginx_template_id=template_id, client_id="tenant-a")

    def statements(self, session):
        return [compiled(c.args[0]) for c in session.execute.call_args_list]

    def test_every_lookup_is_restricted_to_usable_templates(self):
        session = self.session(None, 3, None, None)
        resolve_template(session, self.domain(template_id=9))
        own, client_default, global_default = (
            self.statements(session)[0],
            self.statements(session)[2],
            self.statements(session)[3],
        )
        usable = "nginx_templates.client_id IS NULL OR nginx_templates.client_id = 'tenant-a'"
        assert usable in own
        assert usable in client_default
        assert "nginx_templates.is_default = true" in global_default
        assert "nginx_templates.client_id IS NULL" in global_default
        assert "tenant-a'" not in global_default.split("client_id IS NULL")[-1]


class TestAvailableTemplatesOverHttp:
    """The endpoint is wired, authenticated and checks the client registry."""

    @pytest.mark.asyncio
    async def test_lists_for_an_authenticated_client(self, auth_client, mock_db_session):
        shared = MagicMock(id=1, slug="default", description=None, client_id=None)
        shared.name = "Default"
        result = MagicMock()
        result.scalars.return_value.all.return_value = [shared]
        mock_db_session.execute.return_value = result

        response = await auth_client.get("/api/v1/templates")

        assert response.status_code == 200
        assert response.json() == {
            "items": [
                {"id": 1, "slug": "default", "name": "Default", "description": None, "shared": True}
            ],
            "total": 1,
        }

    @pytest.mark.asyncio
    async def test_requires_a_token(self, client):
        assert (await client.get("/api/v1/templates")).status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_inactive_client_is_refused(self, deactivated_client):  # noqa: F811
        from custom_domain.main import app
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as http:
            response = await http.get("/api/v1/templates")
        assert response.status_code == 403
