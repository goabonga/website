# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the client binding routes (admin scope)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

ADMIN_SCOPE = "billing:admin"


def _one(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _many(items) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


@pytest.fixture
def saas_id() -> str:
    return str(uuid4())


@pytest.fixture
def binding(saas_id) -> MagicMock:
    row = MagicMock()
    row.id = str(uuid4())
    row.saas_app_id = saas_id
    row.client_id = "client-a"
    row.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    return row


@pytest.fixture
async def admin(partitioned_client_factory) -> AsyncClient:
    return await partitioned_client_factory("client-admin", [ADMIN_SCOPE])


class TestListBindings:
    @pytest.mark.asyncio
    async def test_lists_the_clients_of_a_saas(self, admin, mock_db_session, saas_id, binding):
        mock_db_session.execute.side_effect = [_one(MagicMock(id=saas_id)), _many([binding])]

        response = await admin.get(f"/platform/saas/{saas_id}/clients")

        assert response.status_code == 200
        assert [row["client_id"] for row in response.json()] == ["client-a"]
        assert response.json()[0]["saas_app_id"] == saas_id

    @pytest.mark.asyncio
    async def test_unknown_saas(self, admin, mock_db_session):
        mock_db_session.execute.side_effect = [_one(None)]

        response = await admin.get(f"/platform/saas/{uuid4()}/clients")

        assert response.status_code == 404


class TestBindClient:
    @pytest.mark.asyncio
    async def test_creates_a_binding(self, admin, mock_db_session, saas_id):
        saas = MagicMock(id=saas_id, slug="app-a")
        mock_db_session.execute.side_effect = [_one(saas), _one(None)]

        response = await admin.put(f"/platform/saas/{saas_id}/clients/client-a")

        assert response.status_code == 201
        created = mock_db_session.add.call_args[0][0]
        assert (created.saas_app_id, created.client_id) == (saas_id, "client-a")

    @pytest.mark.asyncio
    async def test_is_idempotent(self, admin, mock_db_session, saas_id, binding):
        mock_db_session.execute.side_effect = [_one(MagicMock(id=saas_id)), _one(binding)]

        response = await admin.put(f"/platform/saas/{saas_id}/clients/client-a")

        assert response.status_code == 200
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_saas(self, admin, mock_db_session):
        mock_db_session.execute.side_effect = [_one(None)]

        response = await admin.put(f"/platform/saas/{uuid4()}/clients/client-a")

        assert response.status_code == 404
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_client_id_with_whitespace_is_rejected(self, admin, saas_id):
        response = await admin.put(f"/platform/saas/{saas_id}/clients/bad%20id")

        assert response.status_code == 422


class TestUnbindClient:
    @pytest.mark.asyncio
    async def test_removes_the_binding(self, admin, mock_db_session, saas_id, binding):
        mock_db_session.execute.side_effect = [_one(binding)]

        response = await admin.delete(f"/platform/saas/{saas_id}/clients/client-a")

        assert response.status_code == 204
        mock_db_session.delete.assert_awaited_once_with(binding)

    @pytest.mark.asyncio
    async def test_unknown_binding(self, admin, mock_db_session, saas_id):
        mock_db_session.execute.side_effect = [_one(None)]

        response = await admin.delete(f"/platform/saas/{saas_id}/clients/client-a")

        assert response.status_code == 404


class TestClientSaas:
    @pytest.mark.asyncio
    async def test_lists_the_saas_of_a_client(self, admin, mock_db_session, saas_id):
        mock_db_session.execute.side_effect = [_many([saas_id])]

        response = await admin.get("/platform/clients/client-a/saas")

        assert response.status_code == 200
        assert response.json() == {"client_id": "client-a", "saas_ids": [saas_id]}

    @pytest.mark.asyncio
    async def test_client_without_binding(self, admin, mock_db_session):
        mock_db_session.execute.side_effect = [_many([])]

        response = await admin.get("/platform/clients/client-z/saas")

        assert response.json() == {"client_id": "client-z", "saas_ids": []}


class TestAdminScopeIsRequired:
    """The bindings decide who can act on which SaaS: only the admin scope manages them."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/platform/saas/{s}/clients"),
            ("put", "/platform/saas/{s}/clients/client-a"),
            ("delete", "/platform/saas/{s}/clients/client-a"),
            ("get", "/platform/clients/client-a/saas"),
        ],
    )
    async def test_platform_scopes_are_not_enough(
        self, partitioned_client_factory, mock_db_session, saas_id, method, path
    ):
        """A client bound to the SaaS with every platform scope still cannot rebind clients."""
        client = await partitioned_client_factory(
            "client-a", ["billing:platform:read", "billing:platform:write"]
        )

        response = await getattr(client, method)(path.format(s=saas_id))

        assert response.status_code == 403
        mock_db_session.execute.assert_not_called()
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_authentication_is_required(self, client, saas_id):
        response = await client.put(f"/platform/saas/{saas_id}/clients/client-a")

        assert response.status_code == 401
