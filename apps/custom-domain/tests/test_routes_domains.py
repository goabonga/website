# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/routes/domains.py - Unit tests with mocks."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.models.enums import DomainStatus
from httpx import AsyncClient


class TestListDomains:
    """Tests for list domains endpoint."""

    @pytest.mark.asyncio
    async def test_list_domains_success(self, auth_client: AsyncClient, mock_db_session):
        """Test listing domains for authenticated user."""
        # Mock the execute result for listing
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result
        mock_db_session.scalar.return_value = 0

        response = await auth_client.get("/api/v1/domains")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_domains_include_deleted(self, auth_client: AsyncClient, mock_db_session):
        """Test listing domains with include_deleted=true skips soft-delete filter."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result
        mock_db_session.scalar.return_value = 0

        response = await auth_client.get("/api/v1/domains?include_deleted=true")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_domains_admin_sees_all_clients(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Test that admin user skips client_id filter and sees all domains."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result
        mock_db_session.scalar.return_value = 0

        response = await admin_client.get("/api/v1/domains")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_domains_unauthorized(self, client: AsyncClient):
        """Test listing domains without authentication."""
        response = await client.get("/api/v1/domains")
        assert response.status_code in (401, 403)


class TestCreateDomain:
    """Tests for create domain endpoint."""

    @pytest.mark.asyncio
    async def test_create_domain_success(self, auth_client: AsyncClient, mock_db_session):
        """Test creating a new domain."""
        mock_client = MagicMock()
        mock_client.client_id = "test-client-id"
        mock_client.default_upstream_target = "unix:/var/run/app.sock"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.default_nginx_template_id = None
        mock_client.max_domains = None
        mock_client.is_active = True

        # Mock no existing domain found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Mock count query for domain limit check
        mock_db_session.scalar.return_value = 0

        # Mock refresh to set required attributes
        async def mock_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)

        mock_db_session.refresh = mock_refresh

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=mock_client)
            mock_service.generate_dns_instructions.return_value = {
                "type": "CNAME",
                "host": "@",
                "value": "apps.example.com",
            }

            with patch("custom_domain.tasks.verify_domain_dns") as mock_task:
                mock_task.delay = MagicMock()

                domain_name = f"new-{uuid4().hex[:8]}.example.com"
                response = await auth_client.post(
                    "/api/v1/domains",
                    json={
                        "domain": domain_name,
                        "owner_id": "org_123",
                        "owner_type": "organization",
                    },
                )
                assert response.status_code == 201
                data = response.json()
                assert data["domain"] == domain_name
                assert "dns_instructions" in data

    @pytest.mark.asyncio
    async def test_create_domain_invalid_name(self, auth_client: AsyncClient):
        """Test creating domain with invalid name."""
        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (False, "Invalid domain format")

            response = await auth_client.post(
                "/api/v1/domains",
                json={
                    "domain": "invalid",
                    "owner_id": "org_123",
                    "owner_type": "organization",
                },
            )
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_domain_unauthorized_client(
        self, auth_client: AsyncClient, mock_db_session
    ):
        """Test creating domain with unauthorized client."""
        # Mock no existing domain
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=None)

            response = await auth_client.post(
                "/api/v1/domains",
                json={
                    "domain": "test.example.com",
                    "owner_id": "org_123",
                    "owner_type": "organization",
                },
            )
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_domain_limit_reached(self, auth_client: AsyncClient, mock_db_session):
        """Test creating domain when limit is reached."""
        mock_client = MagicMock()
        mock_client.client_id = "test-client-id"
        mock_client.default_upstream_target = "unix:/var/run/app.sock"
        mock_client.default_cname_target = "apps.example.com"
        mock_client.max_domains = 1
        mock_client.is_active = True

        # Mock no existing domain
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Mock count query to return 1 (limit reached)
        mock_db_session.scalar.return_value = 1

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=mock_client)

            response = await auth_client.post(
                "/api/v1/domains",
                json={
                    "domain": f"limit-test-{uuid4().hex[:8]}.example.com",
                    "owner_id": "org_123",
                    "owner_type": "organization",
                },
            )
            assert response.status_code == 403
            assert "limit" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_domain_duplicate(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test creating domain that already exists."""
        # Mock existing domain found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)

            response = await auth_client.post(
                "/api/v1/domains",
                json={
                    "domain": mock_custom_domain.domain,
                    "owner_id": "org_123",
                    "owner_type": "organization",
                },
            )
            assert response.status_code == 409


class TestGetDomain:
    """Tests for get domain endpoint."""

    @pytest.mark.asyncio
    async def test_get_domain_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting an existing domain."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()
        mock_custom_domain.status = DomainStatus.PENDING
        mock_custom_domain.created_at = datetime.now(UTC)
        mock_custom_domain.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{mock_custom_domain.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_domain_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test getting non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_domain_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{mock_custom_domain.id}")
        assert response.status_code == 403


class TestUpdateDomain:
    """Tests for update domain endpoint."""

    @pytest.mark.asyncio
    async def test_update_domain_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test updating a domain."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()
        mock_custom_domain.status = DomainStatus.PENDING
        mock_custom_domain.upstream_target = "unix:/var/run/app.sock"
        mock_custom_domain.created_at = datetime.now(UTC)
        mock_custom_domain.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.put(
            f"/api/v1/domains/{mock_custom_domain.id}",
            json={"upstream_target": "new-backend:8080"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_domain_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test updating non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.put(
            f"/api/v1/domains/{uuid4()}",
            json={"upstream_target": "new-backend:8080"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_domain_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test updating domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.put(
            f"/api/v1/domains/{mock_custom_domain.id}",
            json={"upstream_target": "new-backend:8080"},
        )
        assert response.status_code == 403


class TestDeleteDomain:
    """Tests for delete domain endpoint."""

    @pytest.mark.asyncio
    async def test_delete_domain_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Deleting only marks the domain and queues the work for a worker."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()
        mock_custom_domain.deleted_at = None
        mock_custom_domain.status = DomainStatus.ACTIVE

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.tasks.deprovision_domain") as mock_task:
            response = await auth_client.delete(f"/api/v1/domains/{mock_custom_domain.id}")

        assert response.status_code == 202
        assert response.json() == {
            "id": str(mock_custom_domain.id),
            "status": "deprovisioning",
            "message": "Deprovisioning started",
        }
        mock_task.delay.assert_called_once_with(str(mock_custom_domain.id))
        assert mock_custom_domain.status == DomainStatus.DEPROVISIONING
        assert mock_custom_domain.deleted_at is None  # the worker soft-deletes it
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_domain_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test deleting non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.delete(f"/api/v1/domains/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_domain_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test deleting domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.delete(f"/api/v1/domains/{mock_custom_domain.id}")
        assert response.status_code == 403


class TestLookupDomain:
    """Tests for lookup domain endpoint."""

    @pytest.mark.asyncio
    async def test_lookup_domain_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test looking up non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get("/api/v1/domains/lookup/nonexistent.example.com")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_lookup_domain_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test looking up existing domain."""
        mock_custom_domain.status = DomainStatus.ACTIVE
        mock_custom_domain.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/lookup/{mock_custom_domain.domain}")
        assert response.status_code == 200


class TestVerifyDomain:
    """Tests for verify domain endpoint."""

    @pytest.mark.asyncio
    async def test_verify_domain_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test triggering DNS verification."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()
        mock_custom_domain.status = DomainStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.tasks.verify_domain_dns") as mock_task:
            mock_task.delay = MagicMock()

            response = await auth_client.post(f"/api/v1/domains/{mock_custom_domain.id}/verify")
            assert response.status_code == 200
            data = response.json()
            assert "verification" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_verify_domain_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test verifying non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.post(f"/api/v1/domains/{uuid4()}/verify")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_verify_domain_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test verifying domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.post(f"/api/v1/domains/{mock_custom_domain.id}/verify")
        assert response.status_code == 403


class TestProvisionDomain:
    """Tests for provision domain endpoint."""

    @pytest.mark.asyncio
    async def test_provision_domain_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test provisioning non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.post(f"/api/v1/domains/{uuid4()}/provision")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_provision_domain_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test provisioning domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.post(f"/api/v1/domains/{mock_custom_domain.id}/provision")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_provision_domain_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test provisioning domain."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()
        mock_custom_domain.status = DomainStatus.DNS_VERIFIED

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.tasks.provision_domain_ssl") as mock_task:
            mock_task.delay = MagicMock()

            response = await auth_client.post(f"/api/v1/domains/{mock_custom_domain.id}/provision")
            assert response.status_code == 200
