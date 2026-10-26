# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/routes/admin/clients.py - Unit tests with mocks."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestListClients:
    """Tests for list clients endpoint."""

    @pytest.mark.asyncio
    async def test_list_clients_success(self, admin_client: AsyncClient, mock_db_session):
        """Test listing clients as admin."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/clients")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_clients_unauthorized(self, auth_client: AsyncClient):
        """Test listing clients without admin scope."""
        response = await auth_client.get("/api/v1/admin/clients")
        assert response.status_code in (401, 403)


class TestCreateClient:
    """Tests for create client endpoint."""

    @pytest.mark.asyncio
    async def test_create_client_success(self, admin_client: AsyncClient, mock_db_session):
        """Test creating a new client."""
        # Mock no existing client with same client_id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Mock refresh to set required attributes
        async def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)

        mock_db_session.refresh = mock_refresh

        client_id = f"new-test-client-{uuid4().hex[:8]}"
        response = await admin_client.post(
            "/api/v1/admin/clients",
            json={
                "client_id": client_id,
                "name": "New Test Client",
                "description": "A new test client",
                "default_upstream_target": "unix:/var/run/app.sock",
                "default_cname_target": "apps.example.com",
                "max_domains": 10,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["client_id"] == client_id
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_client_with_metadata(self, admin_client: AsyncClient, mock_db_session):
        """Test creating a client with metadata."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)

        mock_db_session.refresh = mock_refresh

        client_id = f"meta-client-{uuid4().hex[:8]}"
        response = await admin_client.post(
            "/api/v1/admin/clients",
            json={
                "client_id": client_id,
                "name": "Client with Metadata",
                "default_upstream_target": "unix:/var/run/app.sock",
                "default_cname_target": "apps.example.com",
                "metadata": {"tier": "premium", "features": ["ssl", "cdn"]},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["metadata"] == {"tier": "premium", "features": ["ssl", "cdn"]}

    @pytest.mark.asyncio
    async def test_create_client_duplicate(
        self, admin_client: AsyncClient, mock_db_session, mock_authorized_client
    ):
        """Test creating client with duplicate client_id."""
        # Mock existing client found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_authorized_client
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post(
            "/api/v1/admin/clients",
            json={
                "client_id": mock_authorized_client.client_id,
                "name": "Duplicate Client",
                "description": "Should fail",
                "default_upstream_target": "unix:/var/run/app.sock",
                "default_cname_target": "apps.example.com",
            },
        )
        assert response.status_code == 409


class TestGetClient:
    """Tests for get client endpoint."""

    @pytest.mark.asyncio
    async def test_get_client_success(
        self, admin_client: AsyncClient, mock_db_session, mock_authorized_client
    ):
        """Test getting a client by ID."""
        mock_authorized_client.id = 1
        mock_authorized_client.created_at = datetime.now(UTC)
        mock_authorized_client.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_authorized_client
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get(f"/api/v1/admin/clients/{mock_authorized_client.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_client_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test getting non-existent client."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/clients/99999")
        assert response.status_code == 404


class TestUpdateClient:
    """Tests for update client endpoint."""

    @pytest.mark.asyncio
    async def test_update_client_success(
        self, admin_client: AsyncClient, mock_db_session, mock_authorized_client
    ):
        """Test updating a client."""
        mock_authorized_client.id = 1
        mock_authorized_client.created_at = datetime.now(UTC)
        mock_authorized_client.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_authorized_client
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.put(
            f"/api/v1/admin/clients/{mock_authorized_client.id}",
            json={"name": "Updated Client Name"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_client_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test updating non-existent client."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.put(
            "/api/v1/admin/clients/99999",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404


class TestDeleteClient:
    """Tests for delete client endpoint."""

    @pytest.mark.asyncio
    async def test_delete_client_success(
        self, admin_client: AsyncClient, mock_db_session, mock_authorized_client
    ):
        """Test deleting a client without domains."""
        mock_authorized_client.id = 1
        mock_authorized_client.client_id = "test-client"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_authorized_client
        mock_db_session.execute.return_value = mock_result
        # Mock no domains associated
        mock_db_session.scalar.return_value = 0

        response = await admin_client.delete(f"/api/v1/admin/clients/{mock_authorized_client.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_client_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test deleting non-existent client."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.delete("/api/v1/admin/clients/99999")
        assert response.status_code == 404


class TestDeactivateClient:
    """Tests for deactivate client endpoint."""

    @pytest.mark.asyncio
    async def test_deactivate_client_success(
        self, admin_client: AsyncClient, mock_db_session, mock_authorized_client
    ):
        """Test deactivating a client."""
        mock_authorized_client.id = 1
        mock_authorized_client.is_active = True
        mock_authorized_client.created_at = datetime.now(UTC)
        mock_authorized_client.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_authorized_client
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post(
            f"/api/v1/admin/clients/{mock_authorized_client.id}/deactivate"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_deactivate_client_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test deactivating non-existent client."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post("/api/v1/admin/clients/99999/deactivate")
        assert response.status_code == 404


class TestActivateClient:
    """Tests for activate client endpoint."""

    @pytest.mark.asyncio
    async def test_activate_client_success(
        self, admin_client: AsyncClient, mock_db_session, mock_authorized_client
    ):
        """Test activating a client."""
        mock_authorized_client.id = 1
        mock_authorized_client.is_active = False
        mock_authorized_client.created_at = datetime.now(UTC)
        mock_authorized_client.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_authorized_client
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post(
            f"/api/v1/admin/clients/{mock_authorized_client.id}/activate"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_activate_client_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test activating non-existent client."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post("/api/v1/admin/clients/99999/activate")
        assert response.status_code == 404
