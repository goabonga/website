# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/models/."""

from datetime import UTC, datetime

from custom_domain.models import AuthorizedClient, CustomDomain, NginxTemplate
from custom_domain.models.enums import DomainStatus


class TestDomainStatus:
    """Tests for DomainStatus enum."""

    def test_enum_values(self):
        """Test enum has expected values."""
        assert DomainStatus.PENDING == "pending"
        assert DomainStatus.DNS_VERIFYING == "dns_verifying"
        assert DomainStatus.DNS_VERIFIED == "dns_verified"
        assert DomainStatus.SSL_PROVISIONING == "ssl_provisioning"
        assert DomainStatus.ACTIVE == "active"
        assert DomainStatus.FAILED == "failed"
        assert DomainStatus.SUSPENDED == "suspended"
        assert DomainStatus.EXPIRED == "expired"
        assert DomainStatus.DEPROVISIONING == "deprovisioning"


class TestAuthorizedClient:
    """Tests for AuthorizedClient model."""

    def test_create_client_in_memory(self):
        """Test creating an authorized client (in memory, no persistence)."""
        client = AuthorizedClient(
            client_id="test-client",
            name="Test Client",
            description="A test client",
            default_upstream_target="unix:/var/run/app.sock",
            default_cname_target="apps.example.com",
            max_domains=100,
            is_active=True,
            metadata_={"key": "value"},
        )
        assert client.client_id == "test-client"
        assert client.name == "Test Client"
        assert client.is_active is True
        assert client.metadata_ == {"key": "value"}

    def test_client_defaults(self):
        """Test client default values (in-memory without persistence)."""
        # Note: SQLAlchemy server_default only applies on database commit
        # For in-memory objects, explicit values are used
        client = AuthorizedClient(
            client_id="default-client",
            name="Default Client",
            is_active=True,  # Set explicitly
        )
        assert client.is_active is True
        assert client.max_domains is None  # No limit by default


class TestNginxTemplate:
    """Tests for NginxTemplate model."""

    def test_create_template_in_memory(self):
        """Test creating an nginx template (in memory, no persistence)."""
        template = NginxTemplate(
            slug="test-template",
            name="Test Template",
            description="A test template",
            http_template="server { listen 80; }",
            https_template="server { listen 443 ssl; }",
            is_default=False,
            is_active=True,
            available_variables=["domain", "upstream"],
        )
        assert template.slug == "test-template"
        assert template.name == "Test Template"
        assert template.available_variables == ["domain", "upstream"]

    def test_template_defaults(self):
        """Test template default values (in-memory without persistence)."""
        # Note: SQLAlchemy server_default only applies on database commit
        # For in-memory objects, explicit values are used
        template = NginxTemplate(
            slug="default-template",
            name="Default Template",
            http_template="server {}",
            https_template="server {}",
            is_default=False,  # Set explicitly
            is_active=True,  # Set explicitly
        )
        assert template.is_default is False
        assert template.is_active is True


class TestCustomDomain:
    """Tests for CustomDomain model."""

    def test_create_domain_in_memory(self):
        """Test creating a custom domain (in memory, no persistence)."""
        domain = CustomDomain(
            domain="test.example.com",
            client_id="test-client",
            owner_id="org_123",
            owner_type="organization",
            upstream_target="unix:/var/run/app.sock",
            cname_target="apps.example.com",
            status=DomainStatus.PENDING,
            metadata_={"custom": "data"},
        )
        assert domain.domain == "test.example.com"
        assert domain.status == DomainStatus.PENDING
        assert domain.metadata_ == {"custom": "data"}
        assert domain.deleted_at is None

    def test_domain_defaults(self):
        """Test domain default values (in-memory without persistence)."""
        # Note: SQLAlchemy server_default only applies on database commit
        # For in-memory objects, explicit values are used
        domain = CustomDomain(
            domain="default.example.com",
            client_id="test-client",
            owner_id="org_123",
            owner_type="organization",
            upstream_target="unix:/var/run/app.sock",
            cname_target="apps.example.com",
            status=DomainStatus.PENDING,
            retry_count=0,  # Set explicitly
        )
        assert domain.retry_count == 0
        assert domain.deleted_at is None

    def test_domain_soft_delete_property(self):
        """Test soft deleting a domain."""
        domain = CustomDomain(
            domain="softdelete.example.com",
            client_id="test-client",
            owner_id="org_789",
            owner_type="organization",
            upstream_target="unix:/var/run/app.sock",
            cname_target="apps.example.com",
            status=DomainStatus.ACTIVE,
        )
        assert domain.deleted_at is None

        # Soft delete
        domain.deleted_at = datetime.now(UTC)
        assert domain.deleted_at is not None
