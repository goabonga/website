# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for custom_domain/routes/admin/stats.py (direct function calls)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from custom_domain.auth.dependencies import AuthContext
from custom_domain.auth.models import User
from custom_domain.models.enums import DomainStatus


def _auth(user: User) -> AuthContext:
    """Wrap a User in an AuthContext."""
    return AuthContext(user=user)


def make_admin_user():
    """Create an admin user for testing."""
    return User(
        id=uuid4(),
        email="admin@example.com",
        scopes=["custom-domain:admin"],
        client_id="admin-client",
    )


class TestGetOverviewStats:
    """Unit tests for get_overview_stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_overview_stats_empty(self):
        """Test getting overview stats with no data."""
        from custom_domain.routes.admin.stats import get_overview_stats

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=0)

        user = make_admin_user()
        result = await get_overview_stats(mock_db, _auth(user))

        assert result.domains.total == 0
        assert result.clients.total == 0
        assert result.templates.total == 0

    @pytest.mark.asyncio
    async def test_get_overview_stats_with_data(self):
        """Test getting overview stats with data."""
        from custom_domain.routes.admin.stats import get_overview_stats

        mock_db = AsyncMock()
        # Return different counts for different queries
        call_count = 0

        async def mock_scalar(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Total domains
            if call_count == 1:
                return 100
            # Deleted domains
            elif call_count == 2:
                return 10
            # Status counts (PENDING, DNS_VERIFYING, etc.)
            elif call_count <= 9:
                # PENDING, DNS_VERIFYING, DNS_VERIFIED, SSL_PROVISIONING, ACTIVE, FAILED
                return {3: 5, 4: 3, 5: 2, 6: 1, 7: 70, 8: 9}.get(call_count, 0)
            # Time-based (created_24h, 7d, 30d, activated_24h, 7d)
            elif call_count <= 14:
                return 5
            # SSL stats
            elif call_count <= 16:
                return 2
            # Client stats (total, active)
            elif call_count <= 18:
                return 5
            # Template stats
            else:
                return 3

        mock_db.scalar = mock_scalar

        user = make_admin_user()
        result = await get_overview_stats(mock_db, _auth(user))

        assert result.domains.total == 100
        assert result.domains.deleted == 10
        assert result.domains.active == 70

    @pytest.mark.asyncio
    async def test_get_overview_stats_by_status(self):
        """Test that status counts are populated correctly."""
        from custom_domain.routes.admin.stats import get_overview_stats

        mock_db = AsyncMock()

        # Return values in order of scalar calls
        scalar_values = [
            100,  # total domains
            5,  # deleted domains
            10,  # PENDING
            5,  # DNS_VERIFYING
            3,  # DNS_VERIFIED
            2,  # SSL_PROVISIONING
            50,  # ACTIVE
            15,  # FAILED
            0,  # Any remaining statuses
            8,  # created_24h
            20,  # created_7d
            50,  # created_30d
            5,  # activated_24h
            12,  # activated_7d
            3,  # ssl_expiring
            1,  # ssl_expired
            10,  # total clients
            8,  # active clients
            5,  # total templates
            3,  # active templates
            20,  # domains_with_custom
            30,  # domains_with_default
        ]

        call_idx = 0

        async def mock_scalar(*args, **kwargs):
            nonlocal call_idx
            value = scalar_values[call_idx] if call_idx < len(scalar_values) else 0
            call_idx += 1
            return value

        mock_db.scalar = mock_scalar

        user = make_admin_user()
        result = await get_overview_stats(mock_db, _auth(user))

        # Verify the by_status breakdown
        assert result.domains.by_status[DomainStatus.ACTIVE.value] == 50
        assert result.domains.by_status[DomainStatus.PENDING.value] == 10
        assert result.domains.by_status[DomainStatus.FAILED.value] == 15


class TestGetTopClients:
    """Unit tests for get_top_clients endpoint."""

    @pytest.mark.asyncio
    async def test_get_top_clients_empty(self):
        """Test getting top clients with no data."""
        from custom_domain.routes.admin.stats import get_top_clients

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await get_top_clients(limit=10, db=mock_db, auth=_auth(user))

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_top_clients_with_data(self):
        """Test getting top clients with data."""
        from custom_domain.routes.admin.stats import get_top_clients

        mock_client1 = MagicMock()
        mock_client1.client_id = "client-a"
        mock_client1.name = "Client A"

        mock_client2 = MagicMock()
        mock_client2.client_id = "client-b"
        mock_client2.name = "Client B"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_client1, mock_client2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Return domain counts: client-a has 10 total/5 active, client-b has 5 total/2 active
        scalar_values = [10, 5, 5, 2]
        call_idx = 0

        async def mock_scalar(*args, **kwargs):
            nonlocal call_idx
            value = scalar_values[call_idx] if call_idx < len(scalar_values) else 0
            call_idx += 1
            return value

        mock_db.scalar = mock_scalar

        user = make_admin_user()
        result = await get_top_clients(limit=10, db=mock_db, auth=_auth(user))

        assert len(result) == 2
        # Should be sorted by domain count descending
        assert result[0].client_id == "client-a"
        assert result[0].domain_count == 10
        assert result[1].client_id == "client-b"
        assert result[1].domain_count == 5

    @pytest.mark.asyncio
    async def test_get_top_clients_excludes_zero_domains(self):
        """Test that clients with zero domains are excluded."""
        from custom_domain.routes.admin.stats import get_top_clients

        mock_client = MagicMock()
        mock_client.client_id = "no-domains"
        mock_client.name = "No Domains Client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_client]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=0)  # No domains

        user = make_admin_user()
        result = await get_top_clients(limit=10, db=mock_db, auth=_auth(user))

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_top_clients_respects_limit(self):
        """Test that limit parameter is respected."""
        from custom_domain.routes.admin.stats import get_top_clients

        clients = []
        for i in range(5):
            client = MagicMock()
            client.client_id = f"client-{i}"
            client.name = f"Client {i}"
            clients.append(client)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = clients
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Each client has 10 - i domains
        scalar_values = [10, 5, 9, 4, 8, 3, 7, 2, 6, 1]
        call_idx = 0

        async def mock_scalar(*args, **kwargs):
            nonlocal call_idx
            value = scalar_values[call_idx] if call_idx < len(scalar_values) else 0
            call_idx += 1
            return value

        mock_db.scalar = mock_scalar

        user = make_admin_user()
        result = await get_top_clients(limit=3, db=mock_db, auth=_auth(user))

        assert len(result) == 3


class TestGetRecentActivity:
    """Unit tests for get_recent_activity endpoint."""

    @pytest.mark.asyncio
    async def test_get_recent_activity_empty(self):
        """Test getting recent activity with no data."""
        from custom_domain.routes.admin.stats import get_recent_activity

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await get_recent_activity(limit=20, db=mock_db, auth=_auth(user))

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_recent_activity_with_data(self):
        """Test getting recent activity with data."""
        from custom_domain.routes.admin.stats import get_recent_activity

        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.client_id = "test-client"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.created_at = datetime.now(UTC)
        mock_domain.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_domain]
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await get_recent_activity(limit=20, db=mock_db, auth=_auth(user))

        assert len(result) == 1
        assert result[0].domain == "test.example.com"
        assert result[0].status == DomainStatus.ACTIVE.value


class TestGetDashboard:
    """Unit tests for get_dashboard endpoint."""

    @pytest.mark.asyncio
    async def test_get_dashboard(self):
        """Test getting dashboard data."""
        from custom_domain.routes.admin.stats import get_dashboard

        mock_db = AsyncMock()
        # Mock scalar for overview stats
        mock_db.scalar = AsyncMock(return_value=0)
        # Mock execute for top_clients and recent_activity
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = make_admin_user()
        result = await get_dashboard(mock_db, _auth(user))

        assert result.overview is not None
        assert result.top_clients is not None
        assert result.recent_activity is not None


class TestStatsSettings:
    """Scopes and the expiry window come from settings."""

    def test_scopes_follow_the_setting(self):
        from custom_domain.config import settings
        from custom_domain.routes.admin.stats import ADMIN_SCOPES

        expected = (settings.admin_scope, f"{settings.admin_scope}:stats")
        assert tuple(ADMIN_SCOPES) == expected

    @pytest.mark.asyncio
    async def test_expiring_soon_uses_the_renewal_window(self, monkeypatch):
        from custom_domain.config import settings
        from custom_domain.routes.admin.stats import get_overview_stats

        monkeypatch.setattr(settings, "certificate_renewal_days", 12)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        db.scalar = AsyncMock(return_value=0)
        user = User(id=uuid4(), scopes=["custom-domain:admin"], client_id="ops")
        await get_overview_stats(db, AuthContext(user=user))

        windows = [
            str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
            for call in db.scalar.await_args_list
            if "ssl_expires_at" in str(call.args[0])
        ]
        assert windows, "no expiry query was issued"
        expiry_query = next(w for w in windows if "ssl_expires_at <=" in w)
        soon = (datetime.now(UTC) + timedelta(days=12)).strftime("%Y-%m-%d")
        assert soon in expiry_query
