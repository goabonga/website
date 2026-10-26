# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for custom_domain/routes/domains.py (direct function calls)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.auth.dependencies import AuthContext
from custom_domain.auth.models import User
from custom_domain.models.enums import DomainStatus


def _auth(user: User) -> AuthContext:
    """Wrap a User in an AuthContext."""
    return AuthContext(user=user)


class TestGetDomainOr404:
    """Unit tests for get_domain_or_404 helper function."""

    @pytest.mark.asyncio
    async def test_domain_not_found(self):
        """Test raises 404 when domain not found."""
        from custom_domain.routes.domains import get_domain_or_404
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        with pytest.raises(HTTPException) as exc:
            await get_domain_or_404(mock_db, uuid4(), _auth(user))

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_domain_access_denied(self):
        """Test raises 403 when user doesn't own domain."""
        from custom_domain.routes.domains import get_domain_or_404
        from fastapi import HTTPException

        mock_domain = MagicMock()
        mock_domain.client_id = "other-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        with pytest.raises(HTTPException) as exc:
            await get_domain_or_404(mock_db, uuid4(), _auth(user))

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_domain_found_and_owned(self):
        """Test returns domain when found and owned."""
        from custom_domain.routes.domains import get_domain_or_404

        mock_domain = MagicMock()
        mock_domain.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        result = await get_domain_or_404(mock_db, uuid4(), _auth(user))
        assert result == mock_domain

    @pytest.mark.asyncio
    async def test_include_deleted_skips_filter(self):
        """Test include_deleted=True skips soft-delete filter."""
        from custom_domain.routes.domains import get_domain_or_404

        mock_domain = MagicMock()
        mock_domain.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        result = await get_domain_or_404(mock_db, uuid4(), _auth(user), include_deleted=True)
        assert result == mock_domain

    @pytest.mark.asyncio
    async def test_admin_can_access_any_domain(self):
        """Test admin can access any domain."""
        from custom_domain.routes.domains import get_domain_or_404

        mock_domain = MagicMock()
        mock_domain.client_id = "other-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        admin_user = User(
            id=uuid4(),
            email="admin@example.com",
            scopes=["custom-domain:admin"],
            client_id="admin-client",
        )

        result = await get_domain_or_404(mock_db, uuid4(), _auth(admin_user))
        assert result == mock_domain


class TestListDomains:
    """Unit tests for list_domains endpoint."""

    @pytest.mark.asyncio
    async def test_list_domains_with_filters(self):
        """Test list domains with status and owner filters."""
        from custom_domain.routes.domains import list_domains

        # Create a properly structured mock domain
        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.client_id = "test-client"
        mock_domain.owner_id = "org_123"
        mock_domain.owner_type = "organization"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.created_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_domain]
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        result = await list_domains(
            status_filter=DomainStatus.PENDING,
            owner_id="org_123",
            include_deleted=False,
            limit=20,
            offset=0,
            db=mock_db,
            auth=_auth(user),
        )

        assert result.total == 1
        assert len(result.items) == 1


class TestCreateDomain:
    """Unit tests for create_domain endpoint."""

    @pytest.mark.asyncio
    async def test_create_domain_invalid_domain_name(self):
        """Test create domain fails with invalid domain name."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas.domain import DomainCreate
        from fastapi import HTTPException

        mock_db = AsyncMock()

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        data = DomainCreate(
            domain="invalid..domain",
            owner_id="org_123",
            owner_type="organization",
        )

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (False, "Invalid domain format")

            with pytest.raises(HTTPException) as exc:
                await create_domain(data, mock_db, _auth(user))

            assert exc.value.status_code == 400
            assert "Invalid domain" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_domain_no_client_id(self):
        """Test create domain fails without client_id."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas.domain import DomainCreate
        from fastapi import HTTPException

        mock_db = AsyncMock()

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id=None,  # No client_id
        )

        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)

            # Mock no existing domain
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(HTTPException) as exc:
                await create_domain(data, mock_db, _auth(user))

            assert exc.value.status_code == 403
            assert "Client ID" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_domain_client_not_authorized(self):
        """Test create domain fails when client is not authorized."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas.domain import DomainCreate
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=None)  # Not authorized

            with pytest.raises(HTTPException) as exc:
                await create_domain(data, mock_db, _auth(user))

            assert exc.value.status_code == 403
            assert "not authorized" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_domain_limit_reached(self):
        """Test create domain fails when domain limit is reached."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas.domain import DomainCreate
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing domain
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=10)  # Current count = 10

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        mock_client = MagicMock()
        mock_client.max_domains = 10  # Limit is 10
        mock_client.default_upstream_target = "localhost:8000"
        mock_client.default_cname_target = "apps.example.com"

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=mock_client)

            with pytest.raises(HTTPException) as exc:
                await create_domain(data, mock_db, _auth(user))

            assert exc.value.status_code == 403
            assert "limit reached" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_domain_duplicate(self):
        """Test create domain fails when domain already exists."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas.domain import DomainCreate
        from fastapi import HTTPException

        existing_domain = MagicMock()
        existing_domain.domain = "test.example.com"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_domain  # Domain exists
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)

            with pytest.raises(HTTPException) as exc:
                await create_domain(data, mock_db, _auth(user))

            assert exc.value.status_code == 409
            assert "already registered" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_domain_success(self):
        """Test successful domain creation."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas.domain import DomainCreate

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing domain
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=0)  # Current count = 0
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        def set_domain_attrs(domain):
            domain.id = uuid4()
            domain.domain = "test.example.com"
            domain.status = DomainStatus.PENDING
            domain.cname_target = "apps.example.com"
            domain.owner_id = "org_123"
            domain.owner_type = "organization"
            domain.created_at = datetime.now(UTC)

        mock_db.add = MagicMock(side_effect=lambda d: set_domain_attrs(d))

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        mock_client = MagicMock()
        mock_client.max_domains = 10
        mock_client.default_upstream_target = "localhost:8000"
        mock_client.default_cname_target = "apps.example.com"

        with patch("custom_domain.routes.domains.domain_service") as mock_service:
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=mock_client)

            with patch("custom_domain.tasks.verify_domain_dns") as mock_task:
                mock_task.delay = MagicMock()

                result = await create_domain(data, mock_db, _auth(user))

                assert result.domain == "test.example.com"
                assert result.status == DomainStatus.PENDING
                mock_task.delay.assert_called_once()


class TestGetDomain:
    """Unit tests for get_domain endpoint."""

    @pytest.mark.asyncio
    async def test_get_domain_success(self):
        """Test getting a domain by ID."""
        from custom_domain.routes.domains import get_domain

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.client_id = "test-client"
        mock_domain.owner_id = "org_123"
        mock_domain.owner_type = "organization"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.upstream_target = "localhost:8000"
        mock_domain.nginx_template_id = None
        mock_domain.metadata_ = {}
        mock_domain.error_message = None
        mock_domain.retry_count = 0
        mock_domain.ssl_provisioned_at = None
        mock_domain.ssl_expires_at = None
        mock_domain.last_check_at = None
        mock_domain.created_at = datetime.now(UTC)
        mock_domain.updated_at = datetime.now(UTC)
        mock_domain.deleted_at = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        result = await get_domain(mock_domain.id, mock_db, _auth(user))

        assert result.domain == "test.example.com"
        assert result.status == DomainStatus.ACTIVE


class TestLookupDomain:
    """Unit tests for lookup_domain endpoint."""

    @pytest.mark.asyncio
    async def test_lookup_active_domain(self):
        """Test lookup finds active domain."""
        from custom_domain.routes.domains import lookup_domain

        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.owner_id = "org_123"
        mock_domain.owner_type = "organization"
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.metadata_ = {}

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:lookup"],
            client_id="test-client",
        )

        result = await lookup_domain("test.example.com", mock_db, _auth(user))
        assert result.domain == "test.example.com"

    @pytest.mark.asyncio
    async def test_lookup_domain_not_found(self):
        """Test lookup returns 404 when domain not found."""
        from custom_domain.routes.domains import lookup_domain
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:lookup"],
            client_id="test-client",
        )

        with pytest.raises(HTTPException) as exc:
            await lookup_domain("nonexistent.example.com", mock_db, _auth(user))

        assert exc.value.status_code == 404


class TestUpdateDomain:
    """Unit tests for update_domain endpoint."""

    @pytest.mark.asyncio
    async def test_update_domain_partial_fields(self):
        """Test updating only metadata without upstream_target."""
        from custom_domain.routes.domains import update_domain
        from custom_domain.schemas.domain import DomainUpdate

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.upstream_target = "original:8080"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        data = DomainUpdate(metadata={"key": "value"})

        with patch("custom_domain.routes.domains.DomainResponse") as mock_response:
            mock_response.model_validate.return_value = MagicMock()
            await update_domain(mock_domain.id, data, mock_db, _auth(user))

        assert mock_domain.upstream_target == "original:8080"
        assert mock_domain.metadata_ == {"key": "value"}

    @pytest.mark.asyncio
    async def test_update_domain_all_fields(self):
        """Test updating all fields of a domain."""
        from custom_domain.routes.domains import update_domain
        from custom_domain.schemas.domain import DomainUpdate

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        data = DomainUpdate(
            upstream_target="new-backend:8080",
            nginx_template_id=5,
            metadata={"key": "value"},
        )

        with patch("custom_domain.routes.domains.DomainResponse") as mock_response:
            mock_response.model_validate.return_value = MagicMock()

            await update_domain(mock_domain.id, data, mock_db, _auth(user))

            assert mock_domain.upstream_target == "new-backend:8080"
            assert mock_domain.nginx_template_id == 5
            assert mock_domain.metadata_ == {"key": "value"}


class TestDeleteDomain:
    """Unit tests for delete_domain endpoint."""

    @pytest.mark.asyncio
    async def test_delete_domain_marks_it_deprovisioning(self):
        """The API marks the domain and queues the worker; it never deprovisions itself."""
        from custom_domain.routes.domains import delete_domain

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.deleted_at = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        with patch("custom_domain.tasks.deprovision_domain") as mock_task:
            result = await delete_domain(mock_domain.id, mock_db, _auth(user))

        assert mock_domain.status == DomainStatus.DEPROVISIONING
        assert mock_domain.deleted_at is None
        assert mock_domain.error_message == "Deleted by user"
        mock_task.delay.assert_called_once_with(str(mock_domain.id))
        assert result.status == DomainStatus.DEPROVISIONING
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_domain_twice_queues_again(self):
        """Repeating the request is accepted and queues the (idempotent) work again."""
        from custom_domain.routes.domains import delete_domain

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.DEPROVISIONING

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)
        user = User(id=uuid4(), scopes=["custom-domain:write"], client_id="test-client")

        with patch("custom_domain.tasks.deprovision_domain") as mock_task:
            await delete_domain(mock_domain.id, mock_db, _auth(user))

        mock_task.delay.assert_called_once()
        assert mock_domain.status == DomainStatus.DEPROVISIONING


class TestVerifyDomain:
    """Unit tests for verify_domain endpoint."""

    @pytest.mark.asyncio
    async def test_verify_domain_wrong_status(self):
        """Test verify domain fails for wrong status."""
        from custom_domain.routes.domains import verify_domain
        from fastapi import HTTPException

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.ACTIVE  # Wrong status

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        with pytest.raises(HTTPException) as exc:
            await verify_domain(mock_domain.id, mock_db, _auth(user))

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_domain_success(self):
        """Test verify domain triggers verification."""
        from custom_domain.routes.domains import verify_domain

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.PENDING

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        with patch("custom_domain.tasks.verify_domain_dns") as mock_task:
            mock_task.delay = MagicMock()

            await verify_domain(mock_domain.id, mock_db, _auth(user))

            assert mock_domain.status == DomainStatus.DNS_VERIFYING
            mock_task.delay.assert_called_once()


class TestProvisionDomain:
    """Unit tests for provision_domain endpoint."""

    @pytest.mark.asyncio
    async def test_provision_domain_wrong_status(self):
        """Test provision domain fails for wrong status."""
        from custom_domain.routes.domains import provision_domain
        from fastapi import HTTPException

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.PENDING  # Wrong status

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        with pytest.raises(HTTPException) as exc:
            await provision_domain(mock_domain.id, mock_db, _auth(user))

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_provision_domain_success(self):
        """Test provision domain triggers provisioning."""
        from custom_domain.routes.domains import provision_domain

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:write"],
            client_id="test-client",
        )

        with patch("custom_domain.tasks.provision_domain_ssl") as mock_task:
            mock_task.delay = MagicMock()

            await provision_domain(mock_domain.id, mock_db, _auth(user))

            assert mock_domain.status == DomainStatus.SSL_PROVISIONING
            mock_task.delay.assert_called_once()


def make_test_user(client_id: str = "test-client"):
    """Create a test user for testing."""
    return User(
        id=uuid4(),
        email="test@example.com",
        scopes=["custom-domain:read", "custom-domain:write"],
        client_id=client_id,
    )


class TestGetDomainOr404IncludeDeleted:
    """Test get_domain_or_404 with include_deleted=True (line 41->44)."""

    @pytest.mark.asyncio
    async def test_get_domain_or_404_include_deleted(self):
        """Test getting a deleted domain with include_deleted=True."""
        from custom_domain.routes.domains import get_domain_or_404

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.client_id = "test-client"
        mock_domain.deleted_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_test_user("test-client")

        result = await get_domain_or_404(
            mock_db,
            mock_domain.id,
            _auth(user),
            include_deleted=True,
        )

        assert result == mock_domain


class TestCreateDomainNoMaxDomainsLimit:
    """Test create_domain when client has no max_domains limit (line 151->164)."""

    @pytest.mark.asyncio
    async def test_create_domain_no_max_domains_limit(self):
        """Test creating a domain when client.max_domains is None."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas import DomainCreate

        mock_client = MagicMock()
        mock_client.client_id = "test-client"
        mock_client.max_domains = None  # No limit - this skips line 151-164
        mock_client.default_upstream_target = "unix:/var/run/app.sock"
        mock_client.default_cname_target = "apps.example.com"

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.cname_target = "apps.example.com"
        mock_domain.owner_id = "org_123"
        mock_domain.owner_type = "organization"
        mock_domain.created_at = datetime.now(UTC)

        mock_db = AsyncMock()

        # First call: check for existing domain - returns None
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_existing_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=lambda d: setattr(d, "id", mock_domain.id))

        data = DomainCreate(
            domain="test.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        user = make_test_user("test-client")

        # Mock the tasks module so verify_domain_dns import works
        mock_verify_task = MagicMock()
        mock_verify_task.delay = MagicMock()

        with (
            patch("custom_domain.routes.domains.domain_service") as mock_service,
            patch.dict(
                "sys.modules",
                {"custom_domain.tasks": MagicMock(verify_domain_dns=mock_verify_task)},
            ),
        ):
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=mock_client)

            # We need to handle the domain object creation
            def add_domain(domain):
                domain.id = mock_domain.id
                domain.domain = "test.example.com"
                domain.status = DomainStatus.PENDING
                domain.cname_target = mock_client.default_cname_target
                domain.owner_id = "org_123"
                domain.owner_type = "organization"
                domain.created_at = datetime.now(UTC)

            mock_db.add = MagicMock(side_effect=add_domain)

            result = await create_domain(data, mock_db, _auth(user))

        assert result.domain == "test.example.com"
        # Verify db.scalar was never called (no count query for limit check)
        mock_db.scalar.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_domain_max_domains_zero(self):
        """Test creating a domain when client.max_domains is 0 (falsy, also skips check)."""
        from custom_domain.routes.domains import create_domain
        from custom_domain.schemas import DomainCreate

        mock_client = MagicMock()
        mock_client.client_id = "test-client"
        mock_client.max_domains = 0  # Falsy, also skips line 151-164
        mock_client.default_upstream_target = "unix:/var/run/app.sock"
        mock_client.default_cname_target = "apps.example.com"

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test2.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.cname_target = "apps.example.com"
        mock_domain.owner_id = "org_123"
        mock_domain.owner_type = "organization"
        mock_domain.created_at = datetime.now(UTC)

        mock_db = AsyncMock()

        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_existing_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=lambda d: setattr(d, "id", mock_domain.id))

        data = DomainCreate(
            domain="test2.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        user = make_test_user("test-client")

        mock_verify_task = MagicMock()
        mock_verify_task.delay = MagicMock()

        with (
            patch("custom_domain.routes.domains.domain_service") as mock_service,
            patch.dict(
                "sys.modules",
                {"custom_domain.tasks": MagicMock(verify_domain_dns=mock_verify_task)},
            ),
        ):
            mock_service.validate_domain_name.return_value = (True, None)
            mock_service.get_authorized_client = AsyncMock(return_value=mock_client)

            def add_domain(domain):
                domain.id = mock_domain.id
                domain.domain = "test2.example.com"
                domain.status = DomainStatus.PENDING
                domain.cname_target = mock_client.default_cname_target
                domain.owner_id = "org_123"
                domain.owner_type = "organization"
                domain.created_at = datetime.now(UTC)

            mock_db.add = MagicMock(side_effect=add_domain)

            result = await create_domain(data, mock_db, _auth(user))

        assert result.domain == "test2.example.com"
        mock_db.scalar.assert_not_called()


class TestUpdateDomainWithNoneFields:
    """Test update_domain with None fields (lines 256->259, 259->262, 262->265)."""

    @pytest.mark.asyncio
    async def test_update_domain_all_fields_none(self):
        """Test updating a domain with all optional fields as None."""
        from custom_domain.routes.domains import update_domain
        from custom_domain.schemas import DomainUpdate

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.upstream_target = "unix:/var/run/app.sock"
        mock_domain.nginx_template_id = 1
        mock_domain.metadata_ = {"key": "value"}
        mock_domain.created_at = datetime.now(UTC)
        mock_domain.updated_at = datetime.now(UTC)
        mock_domain.deleted_at = None
        mock_domain.dns_verified_at = None
        mock_domain.ssl_provisioned_at = None
        mock_domain.ssl_expires_at = None
        mock_domain.cname_target = "apps.example.com"
        mock_domain.owner_id = "org_123"
        mock_domain.owner_type = "organization"
        mock_domain.error_message = None
        mock_domain.retry_count = 0
        mock_domain.last_check_at = None

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # DomainUpdate with no fields set (all None)
        data = DomainUpdate()

        user = make_test_user("test-client")

        with patch("custom_domain.routes.domains.get_domain_or_404", return_value=mock_domain):
            await update_domain(mock_domain.id, data, mock_db, _auth(user))

        # The domain fields should remain unchanged
        assert mock_domain.upstream_target == "unix:/var/run/app.sock"
        assert mock_domain.nginx_template_id == 1
        assert mock_domain.metadata_ == {"key": "value"}
