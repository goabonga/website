# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for custom_domain/routes/admin/clients.py (direct function calls)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from custom_domain.auth.models import User
from custom_domain.schemas import ClientCreate, ClientUpdate


def make_admin_user():
    """Create an admin user for testing."""
    return User(
        id=uuid4(),
        email="admin@example.com",
        scopes=["custom-domain:admin"],
        client_id="admin-client",
    )


class TestListClients:
    """Unit tests for list_clients endpoint."""

    @pytest.mark.asyncio
    async def test_list_clients_empty(self):
        """Test listing clients when none exist."""
        from custom_domain.routes.admin.clients import list_clients

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await list_clients(mock_db, user)

        assert result.total == 0
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_list_clients_with_clients(self):
        """Test listing clients with data."""
        from custom_domain.routes.admin.clients import list_clients

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"
        mock_client.name = "Test Client"
        mock_client.default_upstream_target = "http://localhost:8000"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.default_nginx_template_id = None
        mock_client.max_domains = 10
        mock_client.is_active = True
        mock_client.created_at = datetime.now(UTC)

        mock_db = AsyncMock()
        # First call returns clients list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_client]
        mock_db.execute = AsyncMock(return_value=mock_result)
        # Scalar returns domain count
        mock_db.scalar = AsyncMock(return_value=5)

        user = make_admin_user()
        result = await list_clients(mock_db, user)

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].client_id == "test-client"
        assert result.items[0].domains_count == 5


class TestCreateClient:
    """Unit tests for create_client endpoint."""

    @pytest.mark.asyncio
    async def test_create_client_success(self):
        """Test creating a new client."""
        from custom_domain.routes.admin.clients import create_client

        mock_db = AsyncMock()
        # First call checks for existing client
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_existing_result)

        # Mock the created client
        def set_mock_client(client):
            client.id = 1
            client.client_id = "new-client"
            client.name = "New Client"
            client.description = "Test description"
            client.default_upstream_target = "http://localhost:8000"
            client.default_cname_target = "apps.example.com"
            client.default_nginx_template_id = None
            client.max_domains = 10
            client.metadata_ = {}
            client.is_active = True
            client.created_at = datetime.now(UTC)
            client.updated_at = datetime.now(UTC)

        mock_db.add = MagicMock(side_effect=lambda c: set_mock_client(c))
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        data = ClientCreate(
            client_id="new-client",
            name="New Client",
            description="Test description",
            default_upstream_target="http://localhost:8000",
            default_cname_target="apps.example.com",
            max_domains=10,
        )

        user = make_admin_user()
        result = await create_client(data, mock_db, user)

        assert result.client_id == "new-client"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_client_duplicate(self):
        """Test creating a client with duplicate client_id."""
        from custom_domain.routes.admin.clients import create_client
        from fastapi import HTTPException

        mock_existing = MagicMock()
        mock_existing.client_id = "existing-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = ClientCreate(
            client_id="existing-client",
            name="Duplicate Client",
            default_upstream_target="http://localhost:8000",
            default_cname_target="apps.example.com",
        )

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await create_client(data, mock_db, user)

        assert exc.value.status_code == 409
        assert "already exists" in exc.value.detail


class TestGetClient:
    """Unit tests for get_client endpoint."""

    @pytest.mark.asyncio
    async def test_get_client_success(self):
        """Test getting a client by ID."""
        from custom_domain.routes.admin.clients import get_client

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"
        mock_client.name = "Test Client"
        mock_client.description = "Test"
        mock_client.default_upstream_target = "http://localhost:8000"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.default_nginx_template_id = None
        mock_client.max_domains = 10
        mock_client.metadata_ = {}
        mock_client.is_active = True
        mock_client.created_at = datetime.now(UTC)
        mock_client.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await get_client(1, mock_db, user)

        assert result.client_id == "test-client"

    @pytest.mark.asyncio
    async def test_get_client_not_found(self):
        """Test getting a non-existent client."""
        from custom_domain.routes.admin.clients import get_client
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await get_client(999, mock_db, user)

        assert exc.value.status_code == 404


class TestUpdateClient:
    """Unit tests for update_client endpoint."""

    @pytest.mark.asyncio
    async def test_update_client_success(self):
        """Test updating a client."""
        from custom_domain.routes.admin.clients import update_client

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"
        mock_client.name = "Original Name"
        mock_client.description = "Original"
        mock_client.default_upstream_target = "http://localhost:8000"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.default_nginx_template_id = None
        mock_client.max_domains = 10
        mock_client.metadata_ = {}
        mock_client.is_active = True
        mock_client.created_at = datetime.now(UTC)
        mock_client.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        data = ClientUpdate(name="Updated Name")

        user = make_admin_user()
        await update_client(1, data, mock_db, user)

        assert mock_client.name == "Updated Name"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_client_metadata(self):
        """Test updating a client with metadata field."""
        from custom_domain.routes.admin.clients import update_client

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"
        mock_client.name = "Test Client"
        mock_client.description = "Test"
        mock_client.default_upstream_target = "http://localhost:8000"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.default_nginx_template_id = None
        mock_client.max_domains = 10
        mock_client.metadata_ = {}
        mock_client.is_active = True
        mock_client.created_at = datetime.now(UTC)
        mock_client.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        data = ClientUpdate(metadata={"key": "value"})

        user = make_admin_user()
        await update_client(1, data, mock_db, user)

        # metadata field maps to metadata_
        assert mock_client.metadata_ == {"key": "value"}

    @pytest.mark.asyncio
    async def test_update_client_not_found(self):
        """Test updating a non-existent client."""
        from custom_domain.routes.admin.clients import update_client
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = ClientUpdate(name="Updated Name")
        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await update_client(999, data, mock_db, user)

        assert exc.value.status_code == 404


class TestDeleteClient:
    """Unit tests for delete_client endpoint."""

    @pytest.mark.asyncio
    async def test_delete_client_success(self):
        """Test deleting a client with no domains."""
        from custom_domain.routes.admin.clients import delete_client

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=0)  # No domains
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        user = make_admin_user()
        await delete_client(1, mock_db, user)

        mock_db.delete.assert_called_once_with(mock_client)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_client_not_found(self):
        """Test deleting a non-existent client."""
        from custom_domain.routes.admin.clients import delete_client
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await delete_client(999, mock_db, user)

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_client_with_domains(self):
        """Test deleting a client with associated domains."""
        from custom_domain.routes.admin.clients import delete_client
        from fastapi import HTTPException

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=5)  # 5 domains

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await delete_client(1, mock_db, user)

        assert exc.value.status_code == 400
        assert "5 associated domains" in exc.value.detail


class TestDeactivateClient:
    """Unit tests for deactivate_client endpoint."""

    @pytest.mark.asyncio
    async def test_deactivate_client_success(self):
        """Test deactivating a client."""
        from custom_domain.routes.admin.clients import deactivate_client

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"
        mock_client.name = "Test Client"
        mock_client.description = "Test"
        mock_client.default_upstream_target = "http://localhost:8000"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.default_nginx_template_id = None
        mock_client.max_domains = 10
        mock_client.metadata_ = {}
        mock_client.is_active = True
        mock_client.created_at = datetime.now(UTC)
        mock_client.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        user = make_admin_user()
        await deactivate_client(1, mock_db, user)

        assert mock_client.is_active is False
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_client_not_found(self):
        """Test deactivating a non-existent client."""
        from custom_domain.routes.admin.clients import deactivate_client
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await deactivate_client(999, mock_db, user)

        assert exc.value.status_code == 404


class TestActivateClient:
    """Unit tests for activate_client endpoint."""

    @pytest.mark.asyncio
    async def test_activate_client_success(self):
        """Test activating a client."""
        from custom_domain.routes.admin.clients import activate_client

        mock_client = MagicMock()
        mock_client.id = 1
        mock_client.client_id = "test-client"
        mock_client.name = "Test Client"
        mock_client.description = "Test"
        mock_client.default_upstream_target = "http://localhost:8000"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.default_nginx_template_id = None
        mock_client.max_domains = 10
        mock_client.metadata_ = {}
        mock_client.is_active = False
        mock_client.created_at = datetime.now(UTC)
        mock_client.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        user = make_admin_user()
        await activate_client(1, mock_db, user)

        assert mock_client.is_active is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_activate_client_not_found(self):
        """Test activating a non-existent client."""
        from custom_domain.routes.admin.clients import activate_client
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await activate_client(999, mock_db, user)

        assert exc.value.status_code == 404


class TestAdminScopes:
    """The administration scopes derive from the ADMIN_SCOPE setting."""

    def test_scopes_follow_the_setting(self):
        from custom_domain.config import settings
        from custom_domain.routes.admin.clients import ADMIN_SCOPES

        expected = (settings.admin_scope, f"{settings.admin_scope}:clients")
        assert tuple(ADMIN_SCOPES) == expected
