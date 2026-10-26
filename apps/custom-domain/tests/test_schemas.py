# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/schemas/."""

from datetime import UTC, datetime

from custom_domain.schemas import (
    ClientCreate,
    ClientListItem,
    ClientResponse,
    ClientUpdate,
    TemplateCreate,
    TemplateListItem,
    TemplateResponse,
    TemplateUpdate,
)


class TestClientSchemas:
    """Tests for client schemas."""

    def test_client_create(self):
        """Test ClientCreate schema."""
        data = ClientCreate(
            client_id="test-client",
            name="Test Client",
            description="A test",
            default_upstream_target="unix:/var/run/app.sock",
            default_cname_target="apps.example.com",
            max_domains=100,
        )
        assert data.client_id == "test-client"
        assert data.name == "Test Client"

    def test_client_update(self):
        """Test ClientUpdate schema."""
        data = ClientUpdate(name="Updated Name")
        assert data.name == "Updated Name"
        assert data.description is None

    def test_client_response(self):
        """Test ClientResponse schema."""
        now = datetime.now(UTC)
        data = ClientResponse(
            id=1,
            client_id="test",
            name="Test",
            default_upstream_target="unix:/var/run/app.sock",
            default_cname_target="apps.example.com",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        assert data.id == 1

    def test_client_list_item(self):
        """Test ClientListItem schema."""
        now = datetime.now(UTC)
        data = ClientListItem(
            id=1,
            client_id="test",
            name="Test",
            default_upstream_target="unix:/var/run/app.sock",
            default_cname_target="apps.example.com",
            is_active=True,
            domains_count=5,
            created_at=now,
        )
        assert data.domains_count == 5


class TestTemplateSchemas:
    """Tests for template schemas."""

    def test_template_create(self):
        """Test TemplateCreate schema."""
        data = TemplateCreate(
            slug="my-template",
            name="My Template",
            http_template="server {}",
            https_template="server {}",
        )
        assert data.slug == "my-template"

    def test_template_update(self):
        """Test TemplateUpdate schema."""
        data = TemplateUpdate(name="Updated")
        assert data.name == "Updated"

    def test_template_response(self):
        """Test TemplateResponse schema."""
        now = datetime.now(UTC)
        data = TemplateResponse(
            id=1,
            slug="test",
            name="Test",
            http_template="server {}",
            https_template="server {}",
            is_default=False,
            is_active=True,
            available_variables=["domain"],
            created_at=now,
            updated_at=now,
        )
        assert data.available_variables == ["domain"]

    def test_template_list_item(self):
        """Test TemplateListItem schema."""
        now = datetime.now(UTC)
        data = TemplateListItem(
            id=1,
            slug="test",
            name="Test",
            is_default=True,
            is_active=True,
            domains_count=10,
            available_variables=[],
            created_at=now,
        )
        assert data.domains_count == 10
