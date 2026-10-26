# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/schemas/."""

from datetime import UTC, datetime
from uuid import uuid4

from custom_domain.models.enums import DomainStatus
from custom_domain.schemas import (
    ClientCreate,
    ClientListItem,
    ClientResponse,
    ClientUpdate,
    DomainCreate,
    DomainListItem,
    DomainResponse,
    DomainUpdate,
    EventHistoryItem,
    ProgressStep,
    ReprovisionError,
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


class TestDomainSchemas:
    """Tests for domain schemas."""

    def test_domain_create(self):
        """Test DomainCreate schema."""
        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            owner_type="organization",
        )
        assert data.domain == "test.example.com"
        assert data.owner_type == "organization"

    def test_domain_create_with_optionals(self):
        """Test DomainCreate with optional fields."""
        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            upstream_target="unix:/var/run/app.sock",
            cname_target="apps.example.com",
            nginx_template_id=1,
            metadata={"key": "value"},
        )
        assert data.upstream_target == "unix:/var/run/app.sock"
        assert data.metadata == {"key": "value"}

    def test_domain_update(self):
        """Test DomainUpdate schema."""
        data = DomainUpdate(upstream_target="new-upstream")
        assert data.upstream_target == "new-upstream"

    def test_domain_response(self):
        """Test DomainResponse schema."""
        now = datetime.now(UTC)
        data = DomainResponse(
            id=uuid4(),
            domain="test.example.com",
            status=DomainStatus.ACTIVE,
            client_id="client",
            owner_id="org_123",
            owner_type="organization",
            upstream_target="unix:/var/run/app.sock",
            cname_target="apps.example.com",
            created_at=now,
            updated_at=now,
        )
        assert data.status == DomainStatus.ACTIVE

    def test_domain_list_item(self):
        """Test DomainListItem schema."""
        now = datetime.now(UTC)
        data = DomainListItem(
            id=uuid4(),
            domain="test.example.com",
            status=DomainStatus.PENDING,
            owner_id="org_123",
            created_at=now,
        )
        assert data.status == DomainStatus.PENDING


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


class TestEventSchemas:
    """Tests for event schemas."""

    def test_progress_step(self):
        """Test ProgressStep schema."""
        data = ProgressStep(
            current_step="dns_check",
            steps_completed=["init"],
            steps_remaining=["certbot", "nginx"],
            percentage=25,
        )
        assert data.percentage == 25

    def test_event_history_item(self):
        """Test EventHistoryItem schema."""
        now = datetime.now(UTC)
        data = EventHistoryItem(
            type="progress",
            step="dns_check",
            message="DNS verified",
            timestamp=now,
        )
        assert data.type == "progress"

    def test_reprovision_error(self):
        """Test ReprovisionError schema."""
        data = ReprovisionError(
            domain="test.example.com",
            error="Failed to provision",
        )
        assert data.domain == "test.example.com"
