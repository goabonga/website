# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Access and settings rules of custom_domain/routes/events.py."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.auth import AuthContext
from custom_domain.auth.models import User
from custom_domain.config import settings
from custom_domain.main import app
from custom_domain.models.enums import DomainStatus
from custom_domain.routes.events import get_event_history, get_progress_for_status
from httpx import ASGITransport, AsyncClient

from tests.test_routes_access import deactivated_client  # noqa: F401 - fixture

DOMAIN_ID = "00000000-0000-0000-0000-000000000001"


class TestRegistryCheck:
    """The client registry is checked on the events endpoints too."""

    @pytest.mark.parametrize("suffix", ["status", "events", "events/history"])
    @pytest.mark.asyncio
    async def test_inactive_client_gets_403(self, deactivated_client, suffix):  # noqa: F811
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as http:
            response = await http.get(f"/api/v1/domains/{DOMAIN_ID}/{suffix}")
        assert response.status_code == 403
        assert response.json()["detail"] == "Client not authorized"


class TestHistoryLimit:
    """The history can not be read beyond what is kept."""

    @pytest.mark.asyncio
    async def test_limit_is_capped_by_the_history_size(self, monkeypatch):
        monkeypatch.setattr(settings, "event_history_size", 5)
        domain = MagicMock(client_id="tenant-a")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: domain))
        auth = AuthContext(
            user=User(id=uuid4(), scopes=["custom-domain:read"], client_id="tenant-a")
        )
        with patch("custom_domain.routes.events.redis") as mock_redis:
            client = mock_redis.from_url.return_value
            client.lrange = AsyncMock(return_value=[])
            client.llen = AsyncMock(return_value=0)
            client.close = AsyncMock()
            await get_event_history(uuid4(), limit=50, since=None, db=db, auth=auth)
        assert client.lrange.await_args.args[1:] == (0, 4)


class TestProgress:
    """Progress of a domain being deleted."""

    def test_deprovisioning_reports_no_progress(self):
        progress = get_progress_for_status(DomainStatus.DEPROVISIONING)
        assert progress.percentage == 0
        assert progress.current_step is None
