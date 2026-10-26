# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the /api/v1/clients administration routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from mailler.models.client import AuthorizedClient
from sqlalchemy.exc import IntegrityError


def _record(**fields) -> AuthorizedClient:
    now = datetime.now(UTC)
    values = {
        "id": 1,
        "client_id": "app-one",
        "name": "App one",
        "is_active": True,
        "from_email": "app@one.example",
        "from_name": "App One",
        "reply_to": None,
        "allowed_senders": [],
        "allowed_providers": ["brevo"],
        "default_provider": "brevo",
        "rate_limit_per_minute": None,
        "daily_quota": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(fields)
    return AuthorizedClient(**values)


def _list_results(items=None, total=0):
    count = MagicMock()
    count.scalar.return_value = total
    page = MagicMock()
    page.scalars.return_value.all.return_value = items or []
    return [count, page]


async def _refresh(obj, *args, **kwargs):
    now = datetime.now(UTC)
    obj.id = obj.id or 1
    obj.created_at = obj.created_at or now
    obj.updated_at = obj.updated_at or now


class TestAdministrationOnly:
    async def test_regular_clients_are_refused(self, auth_client: AsyncClient, mock_db_session):
        for method, path in (
            ("GET", "/api/v1/clients"),
            ("POST", "/api/v1/clients"),
            ("GET", "/api/v1/clients/app-one"),
            ("PUT", "/api/v1/clients/app-one"),
        ):
            response = await auth_client.request(method, path, json={})
            assert response.status_code == 403, (method, path)
        mock_db_session.add.assert_not_called()

    async def test_unauthenticated_calls_are_refused(self, client: AsyncClient):
        assert (await client.get("/api/v1/clients")).status_code == 401


class TestListClients:
    async def test_list(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_list_results([_record()], total=1))
        response = await admin_client.get("/api/v1/clients")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["client_id"] == "app-one"
        assert data["items"][0]["default_provider"] == "brevo"

    async def test_filters(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_list_results())
        response = await admin_client.get("/api/v1/clients?is_active=false&search=app")
        assert response.status_code == 200
        statement = mock_db_session.execute.await_args_list[1].args[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "authorized_clients.is_active = false" in sql
        assert "%app%" in sql


class TestCreateClient:
    async def test_create(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.refresh = AsyncMock(side_effect=_refresh)
        response = await admin_client.post(
            "/api/v1/clients",
            json={
                "client_id": "app-one",
                "from_email": "app@one.example",
                "from_name": "App One",
                "allowed_senders": [{"email": "alerts@one.example", "name": "Alerts"}],
                "allowed_providers": ["brevo", "ses"],
                "default_provider": "brevo",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["client_id"] == "app-one"
        assert data["is_active"] is True
        stored = mock_db_session.add.call_args[0][0]
        assert stored.allowed_senders == [{"email": "alerts@one.example", "name": "Alerts"}]
        assert stored.allowed_providers == ["brevo", "ses"]

    async def test_duplicate_client(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        response = await admin_client.post("/api/v1/clients", json={"client_id": "app-one"})
        assert response.status_code == 409
        mock_db_session.rollback.assert_awaited_once()

    async def test_unknown_provider_is_refused(self, admin_client: AsyncClient, mock_db_session):
        response = await admin_client.post(
            "/api/v1/clients", json={"client_id": "app-one", "allowed_providers": ["carrier"]}
        )
        assert response.status_code == 422
        response = await admin_client.post(
            "/api/v1/clients", json={"client_id": "app-one", "default_provider": "carrier"}
        )
        assert response.status_code == 422
        mock_db_session.add.assert_not_called()

    async def test_invalid_values_are_refused(self, admin_client: AsyncClient):
        for body in (
            {"client_id": ""},
            {"client_id": "has space"},
            {"client_id": "app", "from_email": "not-an-address"},
            {"client_id": "app", "allowed_senders": [{"email": "nope"}]},
        ):
            assert (await admin_client.post("/api/v1/clients", json=body)).status_code == 422, body


class TestGetClient:
    async def test_found(self, admin_client: AsyncClient, mock_db_session, registry):
        registry.return_value = _record()
        response = await admin_client.get("/api/v1/clients/app-one")
        assert response.status_code == 200
        assert response.json()["from_email"] == "app@one.example"

    async def test_not_found(self, admin_client: AsyncClient, registry):
        registry.return_value = None
        assert (await admin_client.get("/api/v1/clients/nope")).status_code == 404


class TestUpdateClient:
    async def test_partial_update(self, admin_client: AsyncClient, mock_db_session, registry):
        record = _record()
        registry.return_value = record
        response = await admin_client.put(
            "/api/v1/clients/app-one", json={"is_active": False, "name": "Renamed"}
        )
        assert response.status_code == 200
        assert record.is_active is False
        assert record.name == "Renamed"
        assert record.from_email == "app@one.example"

    async def test_senders_and_providers_are_replaced(self, admin_client: AsyncClient, registry):
        record = _record()
        registry.return_value = record
        response = await admin_client.put(
            "/api/v1/clients/app-one",
            json={
                "allowed_senders": [{"email": "alerts@one.example", "name": "Alerts"}],
                "allowed_providers": ["ses"],
            },
        )
        assert response.status_code == 200
        assert record.allowed_senders == [{"email": "alerts@one.example", "name": "Alerts"}]
        assert record.allowed_providers == ["ses"]

    async def test_optional_values_can_be_cleared(self, admin_client: AsyncClient, registry):
        record = _record(reply_to="support@one.example")
        registry.return_value = record
        response = await admin_client.put("/api/v1/clients/app-one", json={"reply_to": None})
        assert response.status_code == 200
        assert record.reply_to is None

    async def test_required_values_ignore_null(self, admin_client: AsyncClient, registry):
        record = _record()
        registry.return_value = record
        await admin_client.put("/api/v1/clients/app-one", json={"is_active": None})
        assert record.is_active is True

    async def test_the_gate_cache_is_cleared(
        self, admin_client: AsyncClient, registry, monkeypatch
    ):
        registry.return_value = _record()
        cleared = MagicMock()
        monkeypatch.setattr("mailler.services.clients.clear_cache", cleared)
        await admin_client.put("/api/v1/clients/app-one", json={"is_active": False})
        cleared.assert_called_once()

    async def test_not_found(self, admin_client: AsyncClient, registry):
        registry.return_value = None
        response = await admin_client.put("/api/v1/clients/nope", json={"name": "x"})
        assert response.status_code == 404


class TestClientLimits:
    async def test_limits_can_be_set_at_registration(
        self, admin_client: AsyncClient, mock_db_session
    ):
        mock_db_session.refresh = AsyncMock(side_effect=_refresh)
        response = await admin_client.post(
            "/api/v1/clients",
            json={"client_id": "app-one", "rate_limit_per_minute": 30, "daily_quota": 5000},
        )
        assert response.status_code == 201
        assert response.json()["rate_limit_per_minute"] == 30
        assert response.json()["daily_quota"] == 5000
        stored = mock_db_session.add.call_args[0][0]
        assert (stored.rate_limit_per_minute, stored.daily_quota) == (30, 5000)

    async def test_clients_are_unlimited_by_default(
        self, admin_client: AsyncClient, mock_db_session
    ):
        mock_db_session.refresh = AsyncMock(side_effect=_refresh)
        response = await admin_client.post("/api/v1/clients", json={"client_id": "app-one"})
        assert response.json()["rate_limit_per_minute"] is None
        assert response.json()["daily_quota"] is None

    async def test_limits_must_be_positive(self, admin_client: AsyncClient):
        for body in (
            {"client_id": "app", "rate_limit_per_minute": 0},
            {"client_id": "app", "daily_quota": -5},
        ):
            assert (await admin_client.post("/api/v1/clients", json=body)).status_code == 422
        assert (
            await admin_client.put("/api/v1/clients/app", json={"daily_quota": 0})
        ).status_code == 422

    async def test_limits_can_be_changed_and_removed(self, admin_client: AsyncClient, registry):
        record = _record(rate_limit_per_minute=10, daily_quota=100)
        registry.return_value = record
        response = await admin_client.put(
            "/api/v1/clients/app-one", json={"rate_limit_per_minute": 20, "daily_quota": None}
        )
        assert response.status_code == 200
        assert record.rate_limit_per_minute == 20
        assert record.daily_quota is None
