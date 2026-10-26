# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations/{org_id}/webhooks endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.is_active = True
    return user


def _make_mock_tenant(tenant_id: uuid.UUID | None = None) -> MagicMock:
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = "test-org"
    tenant.display_name = "Test Organisation"
    tenant.is_active = True
    return tenant


def _make_mock_membership(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    has_scope: bool = True,
) -> MagicMock:
    member = MagicMock()
    member.tenant_id = tenant_id
    member.user_id = user_id
    member.has_scope = MagicMock(return_value=has_scope)
    return member


def _make_mock_webhook(
    webhook_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    *,
    name: str = "Slack",
    url: str = "https://example.com/hook",
    events: list[str] | None = None,
    is_active: bool = True,
) -> MagicMock:
    now = datetime.now(UTC)
    webhook = MagicMock()
    webhook.id = webhook_id or uuid.uuid4()
    webhook.tenant_id = tenant_id or uuid.uuid4()
    webhook.name = name
    webhook.url = url
    webhook.events = events or ["user.created"]
    webhook.secret = "secret"
    webhook.headers = {}
    webhook.is_active = is_active
    webhook.last_triggered_at = None
    webhook.last_status_code = None
    webhook.last_error = None
    webhook.failure_count = 0
    webhook.created_at = now
    webhook.updated_at = now
    return webhook


def _make_mock_delivery(
    webhook_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    status: str = "success",
    response_status: int = 200,
) -> MagicMock:
    now = datetime.now(UTC)
    d = MagicMock()
    d.id = uuid.uuid4()
    d.webhook_id = webhook_id
    d.tenant_id = tenant_id
    d.event = "user.created"
    d.status = status
    d.attempt = 1
    d.max_attempts = 5
    d.request_url = "https://example.com/hook"
    d.request_headers = {"Content-Type": "application/json"}
    d.request_body = {"event": "user.created", "data": {}}
    d.response_status = response_status
    d.response_headers = {"Server": "nginx"}
    d.response_body = "ok"
    d.error = None
    d.duration_ms = 42
    d.delivered_at = now
    d.next_retry_at = None
    d.created_at = now
    return d


@pytest.fixture
def _make_app():
    """Return a factory that creates (app, user) with overridden auth."""
    from auth.main import app as fastapi_app

    created = []

    def factory(user: MagicMock | None = None):
        if user is None:
            user = _make_mock_user()

        async def override_auth():
            return user

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        created.append(fastapi_app)
        return fastapi_app, user

    yield factory

    for a in created:
        a.dependency_overrides.clear()


def _membership_exec_pair(tenant, membership):
    """Build the two execute() results that require_org_membership expects."""
    t_result = MagicMock()
    t_result.scalar_one_or_none.return_value = tenant
    m_result = MagicMock()
    m_result.scalar_one_or_none.return_value = membership
    return [t_result, m_result]


# ---------------------------------------------------------------------------
# GET /events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_webhook_events_success(_make_app):
    """GET /webhooks/events returns the event catalog grouped by prefix."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_membership_exec_pair(tenant, membership))

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/webhooks/events")

    assert response.status_code == 200
    data = response.json()
    assert "user" in data["groups"]
    assert "login" in data["groups"]
    assert "user.created" in data["groups"]["user"]


@pytest.mark.asyncio
async def test_list_webhook_events_forbidden(_make_app):
    """GET /webhooks/events without webhooks:read returns 403."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id, has_scope=False)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_membership_exec_pair(tenant, membership))

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/webhooks/events")

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /webhooks/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_webhooks_success(_make_app):
    """GET /webhooks/ returns paginated list."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)

    mock_db = AsyncMock()

    count_result = MagicMock()
    count_result.scalar.return_value = 1
    list_result = MagicMock()
    list_scalars = MagicMock()
    list_scalars.all.return_value = [webhook]
    list_result.scalars.return_value = list_scalars

    mock_db.execute = AsyncMock(
        side_effect=[
            *_membership_exec_pair(tenant, membership),
            count_result,
            list_result,
        ]
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/webhooks/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Slack"
    # Secret must never leak in responses.
    assert "secret" not in data["items"][0]


@pytest.mark.asyncio
async def test_list_webhooks_forbidden(_make_app):
    """GET /webhooks/ without webhooks:read returns 403."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id, has_scope=False)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_membership_exec_pair(tenant, membership))

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/webhooks/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_webhooks_org_not_found(_make_app):
    """GET /webhooks/ with unknown org returns 404."""
    from auth.api.deps import get_db

    app, _ = _make_app()

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/webhooks/")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /webhooks/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_webhook_success(_make_app):
    """POST /webhooks/ creates and returns the secret exactly once."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_membership_exec_pair(tenant, membership))

    now = datetime.now(UTC)
    added: list = []

    def capture_add(obj):
        added.append(obj)

    mock_db.add = MagicMock(side_effect=capture_add)

    async def mock_flush():
        for obj in added:
            if not hasattr(obj, "_id_set"):
                obj.id = obj.id or uuid.uuid4()
                obj.created_at = now
                obj.updated_at = now
                # Populate SQLAlchemy server/client defaults that only apply
                # on a real flush.
                if getattr(obj, "failure_count", None) is None:
                    obj.failure_count = 0
                obj._id_set = True

    mock_db.flush = AsyncMock(side_effect=mock_flush)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.webhooks.validate_target_url"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/webhooks/",
                json={
                    "name": "Slack",
                    "url": "https://example.com/hook",
                    "events": ["user.created", "login.success"],
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["webhook"]["name"] == "Slack"
    assert data["webhook"]["events"] == ["user.created", "login.success"]
    assert len(data["secret"]) >= 40


@pytest.mark.asyncio
async def test_create_webhook_rejects_invalid_url(_make_app):
    """POST /webhooks/ with unsafe URL returns 400."""
    from auth.api.deps import get_db
    from auth.services.webhook import WebhookURLError

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_membership_exec_pair(tenant, membership))

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(
        "auth.api.routes.api.organisations.webhooks.validate_target_url",
        side_effect=WebhookURLError("private address"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/webhooks/",
                json={
                    "name": "Slack",
                    "url": "http://10.0.0.1/hook",
                    "events": ["user.created"],
                },
            )

    assert response.status_code == 400
    assert "private" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_webhook_rejects_unknown_events(_make_app):
    """POST /webhooks/ with only unknown events returns 400."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_membership_exec_pair(tenant, membership))

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant.id}/webhooks/",
            json={
                "name": "Slack",
                "url": "https://example.com/hook",
                "events": ["fake.event"],
            },
        )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /webhooks/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_webhook_success(_make_app):
    """GET /webhooks/{id} returns the webhook."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    mock_db.execute = AsyncMock(side_effect=[*_membership_exec_pair(tenant, membership), wh_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/webhooks/{webhook.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(webhook.id)


@pytest.mark.asyncio
async def test_get_webhook_not_found(_make_app):
    """GET /webhooks/{id} with unknown id returns 404."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[*_membership_exec_pair(tenant, membership), wh_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/webhooks/{uuid.uuid4()}")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /webhooks/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_webhook_success(_make_app):
    """PATCH /webhooks/{id} applies changes and returns 200."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    mock_db.execute = AsyncMock(side_effect=[*_membership_exec_pair(tenant, membership), wh_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.webhooks.validate_target_url"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/webhooks/{webhook.id}",
                json={
                    "name": "Renamed",
                    "events": ["login.success"],
                    "is_active": False,
                },
            )

    assert response.status_code == 200
    assert webhook.name == "Renamed"
    assert webhook.events == ["login.success"]
    assert webhook.is_active is False


# ---------------------------------------------------------------------------
# DELETE /webhooks/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_webhook_success(_make_app):
    """DELETE /webhooks/{id} removes it and returns 204."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    mock_db.execute = AsyncMock(side_effect=[*_membership_exec_pair(tenant, membership), wh_result])
    mock_db.delete = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant.id}/webhooks/{webhook.id}")

    assert response.status_code == 204
    mock_db.delete.assert_awaited_once_with(webhook)


@pytest.mark.asyncio
async def test_delete_webhook_forbidden(_make_app):
    """DELETE /webhooks/{id} without webhooks:delete returns 403."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id, has_scope=False)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_membership_exec_pair(tenant, membership))

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant.id}/webhooks/{uuid.uuid4()}")

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /webhooks/{id}/rotate-secret
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotate_secret_success(_make_app):
    """POST /webhooks/{id}/rotate-secret returns a new secret."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)
    old_secret = webhook.secret

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    mock_db.execute = AsyncMock(side_effect=[*_membership_exec_pair(tenant, membership), wh_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant.id}/webhooks/{webhook.id}/rotate-secret"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["secret"] != old_secret
    assert webhook.secret == data["secret"]


# ---------------------------------------------------------------------------
# POST /webhooks/{id}/test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_test_ping(_make_app):
    """POST /webhooks/{id}/test enqueues a delivery and returns 202."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    mock_db.execute = AsyncMock(side_effect=[*_membership_exec_pair(tenant, membership), wh_result])
    mock_db.add = MagicMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch("auth.api.routes.api.organisations.webhooks.validate_target_url"),
        patch("auth.tasks.webhooks.deliver_webhook") as deliver,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/webhooks/{webhook.id}/test"
            )

    assert response.status_code == 202
    assert "delivery_id" in response.json()
    deliver.delay.assert_called_once()


# ---------------------------------------------------------------------------
# GET /webhooks/{id}/deliveries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_deliveries_success(_make_app):
    """GET /webhooks/{id}/deliveries returns paginated list."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)
    delivery = _make_mock_delivery(webhook.id, tenant.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    list_result = MagicMock()
    list_scalars = MagicMock()
    list_scalars.all.return_value = [delivery]
    list_result.scalars.return_value = list_scalars

    mock_db.execute = AsyncMock(
        side_effect=[
            *_membership_exec_pair(tenant, membership),
            wh_result,
            count_result,
            list_result,
        ]
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/v1/organisations/{tenant.id}/webhooks/{webhook.id}/deliveries"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["response_status"] == 200


# ---------------------------------------------------------------------------
# POST /webhooks/{id}/deliveries/{delivery_id}/replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_delivery_success(_make_app):
    """POST /webhooks/{id}/deliveries/{did}/replay enqueues a new delivery."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)
    delivery = _make_mock_delivery(webhook.id, tenant.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    original_result = MagicMock()
    original_result.scalar_one_or_none.return_value = delivery
    mock_db.execute = AsyncMock(
        side_effect=[
            *_membership_exec_pair(tenant, membership),
            wh_result,
            original_result,
        ]
    )
    mock_db.add = MagicMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.tasks.webhooks.deliver_webhook") as deliver:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/webhooks/"
                f"{webhook.id}/deliveries/{delivery.id}/replay"
            )

    assert response.status_code == 202
    assert "delivery_id" in response.json()
    deliver.delay.assert_called_once()


@pytest.mark.asyncio
async def test_replay_delivery_not_found(_make_app):
    """POST replay with unknown delivery returns 404."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    webhook = _make_mock_webhook(tenant_id=tenant.id)

    mock_db = AsyncMock()
    wh_result = MagicMock()
    wh_result.scalar_one_or_none.return_value = webhook
    original_result = MagicMock()
    original_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(
        side_effect=[
            *_membership_exec_pair(tenant, membership),
            wh_result,
            original_result,
        ]
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant.id}/webhooks/"
            f"{webhook.id}/deliveries/{uuid.uuid4()}/replay"
        )

    assert response.status_code == 404
