# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the webhook configuration of authorized clients (model, API, CLI)."""

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from alembic import command
from click.testing import CliRunner
from custom_domain.auth import AuthContext
from custom_domain.auth.models import User
from custom_domain.cli import cli
from custom_domain.config import settings
from custom_domain.models import AuthorizedClient
from custom_domain.routes.admin.clients import create_client, update_client
from custom_domain.schemas import ClientCreate, ClientResponse, ClientUpdate
from custom_domain.schemas.validators import validate_webhook_secret, validate_webhook_url
from fastapi import HTTPException
from pydantic import ValidationError

from tests.test_migrations import _config

SECRET = "k" * 32
URL = "https://app.example.com/hooks"


def admin_auth():
    return AuthContext(
        user=User(id=uuid4(), scopes=["custom-domain:admin:clients"], client_id="ops")
    )


def new_client_data(**overrides):
    values = {
        "client_id": "tenant-a",
        "name": "A",
        "default_upstream_target": "/run/a.sock",
        "default_cname_target": "apps.example.com",
    }
    values.update(overrides)
    return ClientCreate(**values)


class TestModelAndMigration:
    def test_columns_are_optional(self):
        table = AuthorizedClient.__table__
        assert table.c.webhook_url.nullable is True
        assert table.c.webhook_secret.nullable is True
        assert AuthorizedClient(client_id="c", name="n").webhook_url is None

    def test_migration(self):
        buffer = io.StringIO()
        command.upgrade(_config(buffer), "002_template_owner:003_client_webhook", sql=True)
        sql = buffer.getvalue()
        assert "ALTER TABLE authorized_clients ADD COLUMN webhook_url VARCHAR(1000)" in sql
        assert "ALTER TABLE authorized_clients ADD COLUMN webhook_secret VARCHAR(255)" in sql

        buffer = io.StringIO()
        command.downgrade(_config(buffer), "003_client_webhook:002_template_owner", sql=True)
        assert "DROP COLUMN webhook_secret" in buffer.getvalue()
        assert "DROP COLUMN webhook_url" in buffer.getvalue()


class TestValidators:
    @pytest.mark.parametrize("url", [URL, "https://hooks.example.com:8443/a?b=c"])
    def test_https_urls_are_accepted(self, url):
        assert validate_webhook_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "http://app.example.com/hooks",
            "ftp://app.example.com",
            "app.example.com/hooks",
            "https://",
            "https://user:pass@app.example.com/",
            "https://" + "a" * 1000 + ".example.com",
        ],
    )
    def test_other_urls_are_refused(self, url):
        with pytest.raises(ValueError):
            validate_webhook_url(url)

    def test_http_is_allowed_only_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "webhook_allow_insecure_urls", True)
        assert validate_webhook_url("http://localhost:9000/hook") == "http://localhost:9000/hook"

    def test_none_passes(self):
        assert validate_webhook_url(None) is None
        assert validate_webhook_secret(None) is None

    def test_short_secrets_are_refused(self):
        assert validate_webhook_secret(SECRET) == SECRET
        with pytest.raises(ValueError, match="32"):
            validate_webhook_secret("short")


class TestSchemas:
    def test_create_validates_both(self):
        assert new_client_data(webhook_url=URL, webhook_secret=SECRET).webhook_url == URL
        with pytest.raises(ValidationError):
            new_client_data(webhook_url="http://x.example.com", webhook_secret=SECRET)
        with pytest.raises(ValidationError):
            new_client_data(webhook_url=URL, webhook_secret="short")

    def test_update_validates_both(self):
        assert ClientUpdate(webhook_url=URL).webhook_url == URL
        with pytest.raises(ValidationError):
            ClientUpdate(webhook_secret="short")

    def test_response_never_carries_the_secret(self):
        client = MagicMock()
        for key, value in {
            "id": 1,
            "client_id": "tenant-a",
            "name": "A",
            "description": None,
            "default_upstream_target": "/run/a.sock",
            "default_cname_target": "apps.example.com",
            "default_nginx_template_id": None,
            "max_domains": None,
            "is_active": True,
            "webhook_url": URL,
            "webhook_secret": SECRET,
            "metadata_": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }.items():
            setattr(client, key, value)

        response = ClientResponse.model_validate(client)
        dumped = response.model_dump()

        assert response.has_webhook_secret is True
        assert response.webhook_url == URL
        assert SECRET not in str(dumped)
        assert "webhook_secret" not in dumped

        client.webhook_secret = None
        assert ClientResponse.model_validate(client).has_webhook_secret is False


def db_with(*values):
    db = AsyncMock()
    results = []
    for value in values:
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        results.append(result)
    db.execute = AsyncMock(side_effect=results)
    db.add = MagicMock()
    return db


class TestRoutes:
    @pytest.mark.asyncio
    async def test_create_stores_the_webhook(self):
        db = db_with(None)

        async def refresh(obj):
            obj.id = 1
            obj.created_at = obj.updated_at = datetime.now(UTC)

        db.refresh = refresh
        result = await create_client(
            new_client_data(webhook_url=URL, webhook_secret=SECRET), db, admin_auth()
        )
        stored = db.add.call_args.args[0]
        assert (stored.webhook_url, stored.webhook_secret) == (URL, SECRET)
        assert result.has_webhook_secret is True
        assert result.webhook_url == URL

    @pytest.mark.asyncio
    async def test_create_refuses_a_url_without_a_secret(self):
        db = db_with(None)
        with pytest.raises(HTTPException) as exc:
            await create_client(new_client_data(webhook_url=URL), db, admin_auth())
        assert exc.value.status_code == 400
        assert "webhook_secret" in exc.value.detail
        db.add.assert_not_called()

    @staticmethod
    def stored_client(**overrides):
        client = MagicMock()
        values = {
            "id": 1,
            "client_id": "tenant-a",
            "name": "A",
            "description": None,
            "default_upstream_target": "/run/a.sock",
            "default_cname_target": "apps.example.com",
            "default_nginx_template_id": None,
            "max_domains": None,
            "is_active": True,
            "webhook_url": None,
            "webhook_secret": None,
            "metadata_": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        values.update(overrides)
        for key, value in values.items():
            setattr(client, key, value)
        return client

    @pytest.mark.asyncio
    async def test_update_sets_and_clears_the_webhook(self):
        client = self.stored_client()
        db = db_with(client)
        db.refresh = AsyncMock()
        await update_client(
            1, ClientUpdate(webhook_url=URL, webhook_secret=SECRET), db, admin_auth()
        )
        assert (client.webhook_url, client.webhook_secret) == (URL, SECRET)

        db = db_with(client)
        db.refresh = AsyncMock()
        await update_client(1, ClientUpdate(webhook_url=None), db, admin_auth())
        assert client.webhook_url is None

    @pytest.mark.asyncio
    async def test_update_refuses_a_url_without_a_secret(self):
        client = self.stored_client()
        db = db_with(client)
        with pytest.raises(HTTPException) as exc:
            await update_client(1, ClientUpdate(webhook_url=URL), db, admin_auth())
        assert exc.value.status_code == 400
        db.commit.assert_not_awaited()


class TestCli:
    @staticmethod
    def invoke(*args, env=None):
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
        session.commit = AsyncMock()
        session.close = AsyncMock()
        with patch("custom_domain.cli.get_session", AsyncMock(return_value=session)):
            result = CliRunner().invoke(
                cli, ["create-client", "--client-id", "c", "--name", "C", *args], env=env
            )
        return result, session

    def test_webhook_options_are_stored(self):
        result, session = self.invoke("--webhook-url", URL, "--webhook-secret", SECRET)
        assert result.exit_code == 0, result.output
        stored = session.add.call_args.args[0]
        assert (stored.webhook_url, stored.webhook_secret) == (URL, SECRET)

    def test_the_secret_can_come_from_the_environment(self):
        result, session = self.invoke(
            "--webhook-url", URL, env={"CUSTOM_DOMAIN_WEBHOOK_SECRET": SECRET}
        )
        assert result.exit_code == 0, result.output
        assert session.add.call_args.args[0].webhook_secret == SECRET

    def test_url_without_secret_is_refused(self):
        result, session = self.invoke("--webhook-url", URL)
        assert result.exit_code == 2
        assert "--webhook-secret" in result.output
        session.add.assert_not_called()

    @pytest.mark.parametrize(
        "args",
        [
            ("--webhook-url", "http://insecure.example.com", "--webhook-secret", SECRET),
            ("--webhook-url", URL, "--webhook-secret", "short"),
        ],
    )
    def test_invalid_values_are_refused(self, args):
        result, session = self.invoke(*args)
        assert result.exit_code == 2
        session.add.assert_not_called()

    def test_listing_shows_the_url_but_not_the_secret(self):
        client = MagicMock(
            client_id="c",
            default_upstream_target=None,
            default_cname_target=None,
            max_domains=None,
            is_active=True,
            webhook_url=URL,
            webhook_secret=SECRET,
        )
        client.name = "C"
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [client]))
        )
        session.close = AsyncMock()
        with patch("custom_domain.cli.get_session", AsyncMock(return_value=session)):
            result = CliRunner().invoke(cli, ["list-clients"])
        assert f"Webhook: {URL}" in result.output
        assert SECRET not in result.output


class TestSdkClientWebhookFields:
    def test_client_dataclass(self):
        from custom_domain.client import Client

        client = Client.from_dict(
            {"id": 1, "client_id": "c", "name": "C", "webhook_url": URL, "has_webhook_secret": True}
        )
        assert (client.webhook_url, client.has_webhook_secret) == (URL, True)
        assert (
            Client.from_dict({"id": 1, "client_id": "c", "name": "C"}).has_webhook_secret is False
        )

    def test_create_and_update_send_the_webhook(self):
        from custom_domain.client import CustomDomainClient

        sdk = CustomDomainClient(base_url="https://api.example.com", access_token="t")
        answer = {"id": 1, "client_id": "c", "name": "C"}
        with patch.object(sdk, "_request", return_value=answer) as mock_req:
            sdk.clients.create("c", "C", webhook_url=URL, webhook_secret=SECRET)
            sdk.clients.update(1, webhook_url=URL, webhook_secret=SECRET)
        created, updated = mock_req.call_args_list
        assert created.kwargs["json"]["webhook_url"] == URL
        assert created.kwargs["json"]["webhook_secret"] == SECRET
        assert updated.kwargs["json"] == {"webhook_url": URL, "webhook_secret": SECRET}
        sdk.close()
