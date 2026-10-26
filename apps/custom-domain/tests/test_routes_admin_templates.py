# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/routes/admin/templates.py - Unit tests with mocks."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestListTemplates:
    """Tests for list templates endpoint."""

    @pytest.mark.asyncio
    async def test_list_templates_success(self, admin_client: AsyncClient, mock_db_session):
        """Test listing templates as admin."""
        # Mock execute for select query
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/templates")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_templates_unauthorized(self, auth_client: AsyncClient):
        """Test listing templates without admin scope."""
        response = await auth_client.get("/api/v1/admin/templates")
        assert response.status_code in (401, 403)


class TestCreateTemplate:
    """Tests for create template endpoint."""

    @pytest.mark.asyncio
    async def test_create_template_success(self, admin_client: AsyncClient, mock_db_session):
        """Test creating a new template."""
        # Mock no existing template (scalar_one_or_none returns None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Mock refresh to set required attributes on the template object
        async def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)

        mock_db_session.refresh = mock_refresh

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_validate_result = MagicMock()
            mock_validate_result.valid = True
            mock_validate_result.errors = []
            mock_service.validate_template.return_value = mock_validate_result

            slug = f"new-template-{uuid4().hex[:8]}"
            response = await admin_client.post(
                "/api/v1/admin/templates",
                json={
                    "slug": slug,
                    "name": "New Template",
                    "description": "Test template",
                    "http_template": "server { listen 80; server_name {{ domain }}; }",
                    "https_template": "server { listen 443 ssl; server_name {{ domain }}; }",
                    "available_variables": ["domain", "upstream"],
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["slug"] == slug

    @pytest.mark.asyncio
    async def test_create_template_duplicate_slug(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test creating template with duplicate slug."""
        # Mock existing template found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post(
            "/api/v1/admin/templates",
            json={
                "slug": mock_nginx_template.slug,
                "name": "Duplicate Template",
                "http_template": "server {}",
                "https_template": "server {}",
            },
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_template_invalid_http_template(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Test creating template with invalid HTTP template syntax."""
        # Mock no existing template
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_validate_result = MagicMock()
            mock_validate_result.valid = False
            mock_validate_result.errors = ["Invalid syntax in HTTP template"]
            mock_service.validate_template.return_value = mock_validate_result

            response = await admin_client.post(
                "/api/v1/admin/templates",
                json={
                    "slug": f"invalid-http-{uuid4().hex[:8]}",
                    "name": "Invalid Template",
                    "http_template": "{{ invalid",
                    "https_template": "server {}",
                },
            )
            assert response.status_code == 400
            assert "HTTP template" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_template_invalid_https_template(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Test creating template with invalid HTTPS template syntax."""
        # Mock no existing template
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            # First call (HTTP) succeeds, second call (HTTPS) fails
            http_result = MagicMock()
            http_result.valid = True
            http_result.errors = []

            https_result = MagicMock()
            https_result.valid = False
            https_result.errors = ["Invalid syntax in HTTPS template"]

            mock_service.validate_template.side_effect = [http_result, https_result]

            response = await admin_client.post(
                "/api/v1/admin/templates",
                json={
                    "slug": f"invalid-https-{uuid4().hex[:8]}",
                    "name": "Invalid HTTPS Template",
                    "http_template": "server { listen 80; }",
                    "https_template": "{{ invalid",
                },
            )
            assert response.status_code == 400
            assert "HTTPS template" in response.json()["detail"]


class TestGetTemplate:
    """Tests for get template endpoint."""

    @pytest.mark.asyncio
    async def test_get_template_success(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test getting a template by ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get(f"/api/v1/admin/templates/{mock_nginx_template.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test getting non-existent template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.get("/api/v1/admin/templates/99999")
        assert response.status_code == 404


class TestUpdateTemplate:
    """Tests for update template endpoint."""

    @pytest.mark.asyncio
    async def test_update_template_success(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test updating a template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.put(
            f"/api/v1/admin/templates/{mock_nginx_template.id}",
            json={"name": "Updated Template Name"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test updating non-existent template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.put(
            "/api/v1/admin/templates/99999",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_template_invalid_http(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test updating template with invalid HTTP template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_validate_result = MagicMock()
            mock_validate_result.valid = False
            mock_validate_result.errors = ["Invalid syntax"]
            mock_service.validate_template.return_value = mock_validate_result

            response = await admin_client.put(
                f"/api/v1/admin/templates/{mock_nginx_template.id}",
                json={"http_template": "{{ invalid"},
            )
            assert response.status_code == 400
            assert "HTTP template" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_template_invalid_https(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test updating template with invalid HTTPS template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_validate_result = MagicMock()
            mock_validate_result.valid = False
            mock_validate_result.errors = ["Invalid syntax"]
            mock_service.validate_template.return_value = mock_validate_result

            response = await admin_client.put(
                f"/api/v1/admin/templates/{mock_nginx_template.id}",
                json={"https_template": "{{ invalid"},
            )
            assert response.status_code == 400
            assert "HTTPS template" in response.json()["detail"]


class TestDeleteTemplate:
    """Tests for delete template endpoint."""

    @pytest.mark.asyncio
    async def test_delete_non_default_template(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test deleting a non-default template."""
        mock_nginx_template.is_default = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result
        # No domains using template
        mock_db_session.scalar.return_value = 0

        response = await admin_client.delete(f"/api/v1/admin/templates/{mock_nginx_template.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test deleting non-existent template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.delete("/api/v1/admin/templates/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_default_template_fails(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test that deleting the default template fails."""
        mock_nginx_template.is_default = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.delete(f"/api/v1/admin/templates/{mock_nginx_template.id}")
        assert response.status_code == 400
        assert "default template" in response.json()["detail"]


class TestValidateTemplate:
    """Tests for validate template endpoint."""

    @pytest.mark.asyncio
    async def test_validate_template_success(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test validating a template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_validate_result = MagicMock()
            mock_validate_result.valid = True
            mock_validate_result.errors = []
            mock_validate_result.rendered_output = "server { server_name test.example.com; }"
            mock_service.validate_template.return_value = mock_validate_result
            mock_service.validate_nginx_syntax_in_worker = AsyncMock(return_value=(True, ""))

            response = await admin_client.post(
                f"/api/v1/admin/templates/{mock_nginx_template.id}/validate",
                json={"test_variables": {"domain": "test.example.com"}},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["nginx_syntax_valid"] is True

    @pytest.mark.asyncio
    async def test_validate_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test validating non-existent template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post(
            "/api/v1/admin/templates/99999/validate",
            json={"test_variables": {}},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_template_http_errors(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test validating template with HTTP template errors."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            # HTTP fails, HTTPS succeeds
            http_result = MagicMock()
            http_result.valid = False
            http_result.errors = ["Missing variable: domain"]

            https_result = MagicMock()
            https_result.valid = True
            https_result.errors = []
            https_result.rendered_output = "server { listen 443; }"

            mock_service.validate_template.side_effect = [http_result, https_result]

            response = await admin_client.post(
                f"/api/v1/admin/templates/{mock_nginx_template.id}/validate",
                json={"test_variables": {}},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_template_https_errors(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test validating template with HTTPS template errors."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            # HTTP succeeds, HTTPS fails
            http_result = MagicMock()
            http_result.valid = True
            http_result.errors = []
            http_result.rendered_output = "server { listen 80; }"

            https_result = MagicMock()
            https_result.valid = False
            https_result.errors = ["Invalid HTTPS config"]

            mock_service.validate_template.side_effect = [http_result, https_result]

            response = await admin_client.post(
                f"/api/v1/admin/templates/{mock_nginx_template.id}/validate",
                json={"test_variables": {}},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_template_nginx_syntax_error(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test validating template with nginx syntax error."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_nginx_template
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            # Both templates render OK
            mock_validate_result = MagicMock()
            mock_validate_result.valid = True
            mock_validate_result.errors = []
            mock_validate_result.rendered_output = "server { listen 80; }"
            mock_service.validate_template.return_value = mock_validate_result
            # But nginx syntax check fails
            mock_service.validate_nginx_syntax_in_worker = AsyncMock(
                return_value=(False, "unexpected }")
            )

            response = await admin_client.post(
                f"/api/v1/admin/templates/{mock_nginx_template.id}/validate",
                json={"test_variables": {"domain": "test.example.com"}},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert any("Nginx syntax" in e for e in data["errors"])


class TestSetDefaultTemplate:
    """Tests for set default template endpoint."""

    @pytest.mark.asyncio
    async def test_set_default_template_success(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test setting a template as default."""
        mock_nginx_template.is_default = False

        # First call: get template by ID
        # Second call: get current defaults
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_nginx_template

        mock_result2 = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result2.scalars.return_value = mock_scalars

        mock_db_session.execute.side_effect = [mock_result1, mock_result2, mock_result2]

        response = await admin_client.post(
            f"/api/v1/admin/templates/{mock_nginx_template.id}/set-default"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_set_default_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test setting non-existent template as default."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post("/api/v1/admin/templates/99999/set-default")
        assert response.status_code == 404


class TestReprovisionDomains:
    """Tests for reprovision domains endpoint."""

    @pytest.mark.asyncio
    async def test_reprovision_dry_run(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test reprovisioning with dry run."""
        # First call: get template by ID
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_nginx_template

        # Second call: get domains using template
        mock_result2 = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result2.scalars.return_value = mock_scalars

        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        response = await admin_client.post(
            f"/api/v1/admin/templates/{mock_nginx_template.id}/reprovision",
            json={"dry_run": True, "only_active": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert "domains_affected" in data
        assert data["success"] == data["domains_affected"]
        assert data["failed"] == 0

    @pytest.mark.asyncio
    async def test_reprovision_template_not_found(self, admin_client: AsyncClient, mock_db_session):
        """Test reprovisioning non-existent template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await admin_client.post(
            "/api/v1/admin/templates/99999/reprovision",
            json={"dry_run": True},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reprovision_actual_run(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test reprovisioning without dry run."""
        # First call: get template by ID
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_nginx_template

        # Second call: get domains using template
        mock_result2 = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result2.scalars.return_value = mock_scalars

        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        with patch("custom_domain.tasks.provision_domain_ssl") as mock_task:
            mock_task.delay = MagicMock()

            response = await admin_client.post(
                f"/api/v1/admin/templates/{mock_nginx_template.id}/reprovision",
                json={"dry_run": False, "only_active": False},
            )
            assert response.status_code == 200
            data = response.json()
            assert "domains_affected" in data

    @pytest.mark.asyncio
    async def test_reprovision_only_active(
        self, admin_client: AsyncClient, mock_db_session, mock_nginx_template
    ):
        """Test reprovisioning only active domains."""
        # First call: get template by ID
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_nginx_template

        # Second call: get domains using template
        mock_result2 = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result2.scalars.return_value = mock_scalars

        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        response = await admin_client.post(
            f"/api/v1/admin/templates/{mock_nginx_template.id}/reprovision",
            json={"dry_run": True, "only_active": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert "domains_affected" in data
