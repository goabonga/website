# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for custom_domain/routes/admin/templates.py (direct function calls)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.auth.models import User
from custom_domain.schemas import (
    TemplateCreate,
    TemplateReprovisionRequest,
    TemplateUpdate,
    TemplateValidateRequest,
)


def make_admin_user():
    """Create an admin user for testing."""
    return User(
        id=uuid4(),
        email="admin@example.com",
        scopes=["custom-domain:admin"],
        client_id="admin-client",
    )


class TestListTemplates:
    """Unit tests for list_templates endpoint."""

    @pytest.mark.asyncio
    async def test_list_templates_empty(self):
        """Test listing templates when none exist."""
        from custom_domain.routes.admin.templates import list_templates

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await list_templates(mock_db, user)

        assert result.total == 0
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_list_templates_with_templates(self):
        """Test listing templates with data."""
        from custom_domain.routes.admin.templates import list_templates

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "default"
        mock_template.name = "Default Template"
        mock_template.description = "The default template"
        mock_template.is_default = True
        mock_template.is_active = True
        mock_template.client_id = None
        mock_template.available_variables = ["domain", "upstream"]
        mock_template.created_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_template]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=3)  # 3 domains using this template

        user = make_admin_user()
        result = await list_templates(mock_db, user)

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].slug == "default"
        assert result.items[0].domains_count == 3


class TestCreateTemplate:
    """Unit tests for create_template endpoint."""

    @pytest.mark.asyncio
    async def test_create_template_success(self):
        """Test creating a new template."""
        from custom_domain.routes.admin.templates import create_template

        mock_db = AsyncMock()
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_existing_result)

        def set_mock_template(template):
            template.id = 1
            template.slug = "custom"
            template.name = "Custom Template"
            template.description = "Custom template"
            template.http_template = "server { listen 80; }"
            template.https_template = "server { listen 443; }"
            template.available_variables = []
            template.is_default = False
            template.is_active = True
            template.created_at = datetime.now(UTC)
            template.updated_at = datetime.now(UTC)

        mock_db.add = MagicMock(side_effect=lambda t: set_mock_template(t))
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        data = TemplateCreate(
            slug="custom",
            name="Custom Template",
            description="Custom template",
            http_template="server { listen 80; }",
            https_template="server { listen 443; }",
        )

        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_result = MagicMock()
            mock_result.valid = True
            mock_service.validate_template.return_value = mock_result

            result = await create_template(data, mock_db, user)

        assert result.slug == "custom"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_template_duplicate_slug(self):
        """Test creating a template with duplicate slug."""
        from custom_domain.routes.admin.templates import create_template
        from fastapi import HTTPException

        mock_existing = MagicMock()
        mock_existing.slug = "existing"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateCreate(
            slug="existing",
            name="Duplicate Template",
            http_template="server { }",
            https_template="server { }",
        )

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await create_template(data, mock_db, user)

        assert exc.value.status_code == 409
        assert "already exists" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_template_invalid_http_template(self):
        """Test creating a template with invalid HTTP template."""
        from custom_domain.routes.admin.templates import create_template
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_existing_result)

        data = TemplateCreate(
            slug="invalid",
            name="Invalid Template",
            http_template="{{ invalid",
            https_template="server { }",
        )

        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_result = MagicMock()
            mock_result.valid = False
            mock_result.errors = ["Syntax error"]
            mock_service.validate_template.return_value = mock_result

            with pytest.raises(HTTPException) as exc:
                await create_template(data, mock_db, user)

        assert exc.value.status_code == 400
        assert "Invalid HTTP template" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_template_invalid_https_template(self):
        """Test creating a template with invalid HTTPS template."""
        from custom_domain.routes.admin.templates import create_template
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_existing_result)

        data = TemplateCreate(
            slug="invalid",
            name="Invalid Template",
            http_template="server { }",
            https_template="{{ invalid",
        )

        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            http_valid = MagicMock()
            http_valid.valid = True
            https_invalid = MagicMock()
            https_invalid.valid = False
            https_invalid.errors = ["Syntax error in HTTPS"]
            mock_service.validate_template.side_effect = [http_valid, https_invalid]

            with pytest.raises(HTTPException) as exc:
                await create_template(data, mock_db, user)

        assert exc.value.status_code == 400
        assert "Invalid HTTPS template" in exc.value.detail


class TestGetTemplate:
    """Unit tests for get_template endpoint."""

    @pytest.mark.asyncio
    async def test_get_template_success(self):
        """Test getting a template by ID."""
        from custom_domain.routes.admin.templates import get_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "default"
        mock_template.name = "Default Template"
        mock_template.description = "Default"
        mock_template.http_template = "server { }"
        mock_template.https_template = "server { ssl on; }"
        mock_template.available_variables = []
        mock_template.is_default = True
        mock_template.is_active = True
        mock_template.client_id = None
        mock_template.created_at = datetime.now(UTC)
        mock_template.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await get_template(1, mock_db, user)

        assert result.slug == "default"

    @pytest.mark.asyncio
    async def test_get_template_not_found(self):
        """Test getting a non-existent template."""
        from custom_domain.routes.admin.templates import get_template
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await get_template(999, mock_db, user)

        assert exc.value.status_code == 404


class TestUpdateTemplate:
    """Unit tests for update_template endpoint."""

    @pytest.mark.asyncio
    async def test_update_template_success(self):
        """Test updating a template."""
        from custom_domain.routes.admin.templates import update_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "default"
        mock_template.name = "Original Name"
        mock_template.description = "Original"
        mock_template.http_template = "server { }"
        mock_template.https_template = "server { ssl on; }"
        mock_template.available_variables = []
        mock_template.is_default = True
        mock_template.is_active = True
        mock_template.client_id = None
        mock_template.created_at = datetime.now(UTC)
        mock_template.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        data = TemplateUpdate(name="Updated Name")

        user = make_admin_user()
        await update_template(1, data, mock_db, user)

        assert mock_template.name == "Updated Name"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_template_http_template(self):
        """Test updating template with new HTTP template."""
        from custom_domain.routes.admin.templates import update_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "default"
        mock_template.name = "Default"
        mock_template.description = "Default"
        mock_template.http_template = "server { }"
        mock_template.https_template = "server { ssl on; }"
        mock_template.available_variables = []
        mock_template.is_default = True
        mock_template.is_active = True
        mock_template.client_id = None
        mock_template.created_at = datetime.now(UTC)
        mock_template.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        data = TemplateUpdate(http_template="server { listen 80; }")

        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_valid = MagicMock()
            mock_valid.valid = True
            mock_service.validate_template.return_value = mock_valid

            await update_template(1, data, mock_db, user)

        assert mock_template.http_template == "server { listen 80; }"

    @pytest.mark.asyncio
    async def test_update_template_invalid_http_template(self):
        """Test updating template with invalid HTTP template."""
        from custom_domain.routes.admin.templates import update_template
        from fastapi import HTTPException

        mock_template = MagicMock()
        mock_template.id = 1

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateUpdate(http_template="{{ invalid")

        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_invalid = MagicMock()
            mock_invalid.valid = False
            mock_invalid.errors = ["Syntax error"]
            mock_service.validate_template.return_value = mock_invalid

            with pytest.raises(HTTPException) as exc:
                await update_template(1, data, mock_db, user)

        assert exc.value.status_code == 400
        assert "Invalid HTTP template" in exc.value.detail

    @pytest.mark.asyncio
    async def test_update_template_invalid_https_template(self):
        """Test updating template with invalid HTTPS template."""
        from custom_domain.routes.admin.templates import update_template
        from fastapi import HTTPException

        mock_template = MagicMock()
        mock_template.id = 1

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateUpdate(https_template="{{ invalid")

        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_invalid = MagicMock()
            mock_invalid.valid = False
            mock_invalid.errors = ["Syntax error"]
            mock_service.validate_template.return_value = mock_invalid

            with pytest.raises(HTTPException) as exc:
                await update_template(1, data, mock_db, user)

        assert exc.value.status_code == 400
        assert "Invalid HTTPS template" in exc.value.detail

    @pytest.mark.asyncio
    async def test_update_template_not_found(self):
        """Test updating a non-existent template."""
        from custom_domain.routes.admin.templates import update_template
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateUpdate(name="Updated Name")
        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await update_template(999, data, mock_db, user)

        assert exc.value.status_code == 404


class TestDeleteTemplate:
    """Unit tests for delete_template endpoint."""

    @pytest.mark.asyncio
    async def test_delete_template_success(self):
        """Test deleting a template with no domains."""
        from custom_domain.routes.admin.templates import delete_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "custom"
        mock_template.is_default = False

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=0)  # No domains
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        user = make_admin_user()
        await delete_template(1, mock_db, user)

        mock_db.delete.assert_called_once_with(mock_template)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_template_not_found(self):
        """Test deleting a non-existent template."""
        from custom_domain.routes.admin.templates import delete_template
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await delete_template(999, mock_db, user)

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_default_template(self):
        """Test deleting the default template."""
        from custom_domain.routes.admin.templates import delete_template
        from fastapi import HTTPException

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.is_default = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await delete_template(1, mock_db, user)

        assert exc.value.status_code == 400
        assert "default template" in exc.value.detail

    @pytest.mark.asyncio
    async def test_delete_template_with_domains(self):
        """Test deleting a template with associated domains."""
        from custom_domain.routes.admin.templates import delete_template
        from fastapi import HTTPException

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.is_default = False

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=5)  # 5 domains

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await delete_template(1, mock_db, user)

        assert exc.value.status_code == 400
        assert "5 associated domains" in exc.value.detail


class TestValidateTemplate:
    """Unit tests for validate_template endpoint."""

    @pytest.mark.asyncio
    async def test_validate_template_success(self):
        """Test validating a template successfully."""
        from custom_domain.routes.admin.templates import validate_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.http_template = "server { listen 80; }"
        mock_template.https_template = "server { listen 443; }"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateValidateRequest(test_variables={"domain": "test.com"})
        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_valid = MagicMock()
            mock_valid.valid = True
            mock_valid.rendered_output = "server { listen 80; }"
            mock_service.validate_template.return_value = mock_valid
            mock_service.validate_nginx_syntax_in_worker = AsyncMock(return_value=(True, None))

            result = await validate_template(1, data, mock_db, user)

        assert result.valid is True
        assert result.nginx_syntax_valid is True

    @pytest.mark.asyncio
    async def test_validate_template_with_errors(self):
        """Test validating a template with errors."""
        from custom_domain.routes.admin.templates import validate_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.http_template = "{{ invalid"
        mock_template.https_template = "server { }"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateValidateRequest(test_variables={})
        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            http_invalid = MagicMock()
            http_invalid.valid = False
            http_invalid.errors = ["HTTP template error"]
            https_valid = MagicMock()
            https_valid.valid = True
            https_valid.rendered_output = "server { }"
            mock_service.validate_template.side_effect = [http_invalid, https_valid]

            result = await validate_template(1, data, mock_db, user)

        assert result.valid is False
        assert "HTTP template error" in result.errors

    @pytest.mark.asyncio
    async def test_validate_template_https_errors_only(self):
        """Test validating a template with HTTPS errors only.

        This tests the case where HTTP template is valid but HTTPS template
        has validation errors (covers line 258 in templates.py).
        """
        from custom_domain.routes.admin.templates import validate_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.http_template = "server { }"
        mock_template.https_template = "{{ invalid"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateValidateRequest(test_variables={})
        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            http_valid = MagicMock()
            http_valid.valid = True
            http_valid.rendered_output = "server { }"
            https_invalid = MagicMock()
            https_invalid.valid = False
            https_invalid.errors = ["HTTPS template error", "Another HTTPS error"]
            mock_service.validate_template.side_effect = [http_valid, https_invalid]

            result = await validate_template(1, data, mock_db, user)

        assert result.valid is False
        assert "HTTPS template error" in result.errors
        assert "Another HTTPS error" in result.errors

    @pytest.mark.asyncio
    async def test_validate_template_nginx_syntax_error(self):
        """Test validating a template with nginx syntax errors."""
        from custom_domain.routes.admin.templates import validate_template

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.http_template = "server { }"
        mock_template.https_template = "server { }"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateValidateRequest(test_variables={})
        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            mock_valid = MagicMock()
            mock_valid.valid = True
            mock_valid.rendered_output = "server { }"
            mock_service.validate_template.return_value = mock_valid
            mock_service.validate_nginx_syntax_in_worker = AsyncMock(
                return_value=(False, "nginx: invalid directive")
            )

            result = await validate_template(1, data, mock_db, user)

        assert result.valid is False
        assert "Nginx syntax error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_template_not_found(self):
        """Test validating a non-existent template."""
        from custom_domain.routes.admin.templates import validate_template
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateValidateRequest(test_variables={})
        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await validate_template(999, data, mock_db, user)

        assert exc.value.status_code == 404


class TestSetDefaultTemplate:
    """Unit tests for set_default_template endpoint."""

    @pytest.mark.asyncio
    async def test_set_default_template_success(self):
        """Test setting a template as default."""
        from custom_domain.routes.admin.templates import set_default_template

        mock_template = MagicMock()
        mock_template.id = 2
        mock_template.slug = "new-default"
        mock_template.name = "New Default"
        mock_template.description = "New default"
        mock_template.http_template = "server { }"
        mock_template.https_template = "server { }"
        mock_template.available_variables = []
        mock_template.is_default = False
        mock_template.is_active = True
        mock_template.client_id = None
        mock_template.created_at = datetime.now(UTC)
        mock_template.updated_at = datetime.now(UTC)

        mock_current_default = MagicMock()
        mock_current_default.is_default = True

        mock_db = AsyncMock()
        # First execute returns the template to set as default
        mock_template_result = MagicMock()
        mock_template_result.scalar_one_or_none.return_value = mock_template

        # Second and third execute return current defaults
        mock_defaults_result = MagicMock()
        mock_defaults_result.scalars.return_value.all.return_value = [mock_current_default]

        mock_db.execute = AsyncMock(
            side_effect=[mock_template_result, mock_defaults_result, mock_defaults_result]
        )
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        user = make_admin_user()
        await set_default_template(2, mock_db, user)

        assert mock_template.is_default is True
        assert mock_current_default.is_default is False
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_default_template_not_found(self):
        """Test setting a non-existent template as default."""
        from custom_domain.routes.admin.templates import set_default_template
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await set_default_template(999, mock_db, user)

        assert exc.value.status_code == 404


class TestReprovisionDomains:
    """Unit tests for reprovision_domains endpoint."""

    @pytest.mark.asyncio
    async def test_reprovision_domains_dry_run(self):
        """Test reprovisioning domains in dry run mode."""
        from custom_domain.routes.admin.templates import reprovision_domains

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "default"

        mock_domain1 = MagicMock()
        mock_domain1.id = uuid4()
        mock_domain1.domain = "test1.example.com"
        mock_domain2 = MagicMock()
        mock_domain2.id = uuid4()
        mock_domain2.domain = "test2.example.com"

        mock_db = AsyncMock()
        mock_template_result = MagicMock()
        mock_template_result.scalar_one_or_none.return_value = mock_template
        mock_domains_result = MagicMock()
        mock_domains_result.scalars.return_value.all.return_value = [
            mock_domain1,
            mock_domain2,
        ]
        mock_db.execute = AsyncMock(side_effect=[mock_template_result, mock_domains_result])

        data = TemplateReprovisionRequest(dry_run=True, only_active=False)
        user = make_admin_user()

        result = await reprovision_domains(1, data, mock_db, user)

        assert result.domains_affected == 2
        assert result.success == 2
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_reprovision_domains_actual_run(self):
        """Test reprovisioning domains for real."""
        from custom_domain.routes.admin.templates import reprovision_domains

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "default"

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"

        mock_db = AsyncMock()
        mock_template_result = MagicMock()
        mock_template_result.scalar_one_or_none.return_value = mock_template
        mock_domains_result = MagicMock()
        mock_domains_result.scalars.return_value.all.return_value = [mock_domain]
        mock_db.execute = AsyncMock(side_effect=[mock_template_result, mock_domains_result])

        data = TemplateReprovisionRequest(dry_run=False, only_active=True)
        user = make_admin_user()

        with patch("custom_domain.tasks.provision_domain_ssl") as mock_task:
            mock_task.delay = MagicMock()
            result = await reprovision_domains(1, data, mock_db, user)

        assert result.domains_affected == 1
        assert result.success == 1
        assert result.failed == 0
        mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_reprovision_domains_with_failure(self):
        """Test reprovisioning domains with some failures."""
        from custom_domain.routes.admin.templates import reprovision_domains

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "default"

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"

        mock_db = AsyncMock()
        mock_template_result = MagicMock()
        mock_template_result.scalar_one_or_none.return_value = mock_template
        mock_domains_result = MagicMock()
        mock_domains_result.scalars.return_value.all.return_value = [mock_domain]
        mock_db.execute = AsyncMock(side_effect=[mock_template_result, mock_domains_result])

        data = TemplateReprovisionRequest(dry_run=False, only_active=False)
        user = make_admin_user()

        with patch("custom_domain.tasks.provision_domain_ssl") as mock_task:
            mock_task.delay = MagicMock(side_effect=Exception("Task failed"))
            result = await reprovision_domains(1, data, mock_db, user)

        assert result.domains_affected == 1
        assert result.success == 0
        assert result.failed == 1
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_reprovision_domains_not_found(self):
        """Test reprovisioning domains for a non-existent template."""
        from custom_domain.routes.admin.templates import reprovision_domains
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = TemplateReprovisionRequest(dry_run=True, only_active=False)
        user = make_admin_user()

        with pytest.raises(HTTPException) as exc:
            await reprovision_domains(999, data, mock_db, user)

        assert exc.value.status_code == 404


class TestUpdateTemplateValidHttpsTemplate:
    """Test update_template when https_template is provided and valid (line 165->171)."""

    @pytest.mark.asyncio
    async def test_update_template_with_valid_https_template(self):
        """Test updating a template with a valid https_template."""
        from custom_domain.routes.admin.templates import update_template
        from custom_domain.schemas import TemplateUpdate

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "custom"
        mock_template.name = "Custom Template"
        mock_template.description = "Custom template"
        mock_template.http_template = "server { listen 80; }"
        mock_template.https_template = "server { listen 443; }"
        mock_template.available_variables = []
        mock_template.is_default = False
        mock_template.is_active = True
        mock_template.client_id = None
        mock_template.created_at = datetime.now(UTC)
        mock_template.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Only update https_template (to trigger line 165)
        data = TemplateUpdate(https_template="server { listen 443 ssl; }")

        user = make_admin_user()

        with patch("custom_domain.routes.admin.templates.template_service") as mock_service:
            # Make validation return valid
            mock_valid_result = MagicMock()
            mock_valid_result.valid = True
            mock_service.validate_template.return_value = mock_valid_result

            result = await update_template(1, data, mock_db, user)

        assert result.slug == "custom"
        mock_db.commit.assert_called_once()
        # Verify the template was updated
        assert mock_template.https_template == "server { listen 443 ssl; }"


class TestAdminScopes:
    """The administration scopes derive from the ADMIN_SCOPE setting."""

    def test_scopes_follow_the_setting(self):
        from custom_domain.config import settings
        from custom_domain.routes.admin.templates import ADMIN_SCOPES

        assert (settings.admin_scope, f"{settings.admin_scope}:templates") == ADMIN_SCOPES
