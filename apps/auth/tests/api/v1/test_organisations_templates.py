# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations/{org_id}/templates endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


def _make_mock_tenant(tenant_id: uuid.UUID | None = None) -> MagicMock:
    """Build a mock Tenant."""
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = "test-org"
    tenant.display_name = "Test Organisation"
    tenant.is_active = True
    return tenant


def _make_mock_membership(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> MagicMock:
    """Build a mock TenantMember with templates scope."""
    member = MagicMock()
    member.tenant_id = tenant_id
    member.user_id = user_id

    def has_scope(s: str) -> bool:
        return s.startswith("templates:") or s == "*"

    member.has_scope = MagicMock(side_effect=has_scope)
    return member


def _make_mock_template(
    tenant_id: uuid.UUID,
    template_name: str = "auth/login.html",
    content: str = "<html>Custom Login</html>",
) -> MagicMock:
    """Build a mock TenantTemplate."""
    tmpl = MagicMock()
    tmpl.id = uuid.uuid4()
    tmpl.tenant_id = tenant_id
    tmpl.template_name = template_name
    tmpl.content = content
    tmpl.is_active = True
    tmpl.description = None
    tmpl.created_at = datetime.now(UTC)
    tmpl.updated_at = datetime.now(UTC)
    return tmpl


@pytest.fixture
def _make_app():
    """Return a factory that yields (app, user) with mocked auth."""
    from auth.main import app as fastapi_app

    created = []

    def factory(user: MagicMock | None = None):
        if user is None:
            user_ = MagicMock()
            user_.id = uuid.uuid4()
            user_.is_active = True
        else:
            user_ = user

        async def override_auth():
            return user_

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        created.append(fastapi_app)
        return fastapi_app, user_

    yield factory

    for a in created:
        a.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/organisations/{org_id}/templates/
# ===========================================================================


@pytest.mark.asyncio
async def test_list_templates_success(_make_app):
    """GET templates/ returns list of templates."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    tmpl1 = _make_mock_template(tenant_id, "auth/login.html")
    tmpl2 = _make_mock_template(tenant_id, "auth/register.html", "<html>Register</html>")

    mock_db = AsyncMock()

    # require_org_membership queries
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    # List templates query
    templates_result = MagicMock()
    templates_scalars = MagicMock()
    templates_scalars.all.return_value = [tmpl1, tmpl2]
    templates_result.scalars.return_value = templates_scalars

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, templates_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/templates/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_templates_empty(_make_app):
    """GET templates/ returns empty list when no templates exist."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    templates_result = MagicMock()
    templates_scalars = MagicMock()
    templates_scalars.all.return_value = []
    templates_result.scalars.return_value = templates_scalars

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, templates_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/templates/")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_templates_not_member(_make_app):
    """GET templates/ returns 403 when user is not a member."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/templates/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_templates_unauthenticated():
    """GET templates/ without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/templates/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_templates_missing_scope(_make_app):
    """GET templates/ returns 403 when member lacks templates:read scope."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)

    membership = MagicMock()
    membership.tenant_id = tenant_id
    membership.user_id = user.id
    membership.has_scope = MagicMock(return_value=False)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/templates/")

    assert response.status_code == 403


# ===========================================================================
# GET /api/v1/organisations/{org_id}/templates/{template_name}
# ===========================================================================


@pytest.mark.asyncio
async def test_get_template_success(_make_app):
    """GET templates/{name} returns template."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    tmpl = _make_mock_template(tenant_id, "auth/login.html")

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = tmpl

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/templates/auth/login.html")

    assert response.status_code == 200
    data = response.json()
    assert data["template_name"] == "auth/login.html"
    assert data["content"] == "<html>Custom Login</html>"


@pytest.mark.asyncio
async def test_get_template_not_found(_make_app):
    """GET templates/{name} returns 404 when template doesn't exist."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/templates/nonexistent.html")

    assert response.status_code == 404


# ===========================================================================
# PUT /api/v1/organisations/{org_id}/templates/{template_name}
# ===========================================================================


@pytest.mark.asyncio
async def test_update_template_create(_make_app):
    """PUT templates/{name} creates a new template."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    # No existing template
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    created_tmpl = _make_mock_template(tenant_id, "auth/login.html", "<html>New</html>")

    async def mock_refresh(obj, *args, **kwargs):
        for attr in [
            "id",
            "tenant_id",
            "template_name",
            "content",
            "is_active",
            "description",
            "created_at",
            "updated_at",
        ]:
            setattr(obj, attr, getattr(created_tmpl, attr))

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            f"/api/v1/organisations/{tenant_id}/templates/auth/login.html",
            json={"content": "<html>New</html>"},
        )

    assert response.status_code == 200
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_template_existing(_make_app):
    """PUT templates/{name} updates existing template."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    existing_tmpl = _make_mock_template(tenant_id, "auth/login.html")

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = existing_tmpl

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            f"/api/v1/organisations/{tenant_id}/templates/auth/login.html",
            json={
                "content": "<html>Updated</html>",
                "description": "Custom login page",
                "is_active": False,
            },
        )

    assert response.status_code == 200
    assert existing_tmpl.content == "<html>Updated</html>"
    assert existing_tmpl.description == "Custom login page"
    assert existing_tmpl.is_active is False
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_template_validation_error(_make_app):
    """PUT templates/{name} with empty content returns 422."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            f"/api/v1/organisations/{tenant_id}/templates/auth/login.html",
            json={"content": ""},  # empty content, min_length=1
        )

    assert response.status_code == 422


# ===========================================================================
# DELETE /api/v1/organisations/{org_id}/templates/{template_name}
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_template_success(_make_app):
    """DELETE templates/{name} returns 204."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    tmpl = _make_mock_template(tenant_id, "auth/login.html")

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = tmpl

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant_id}/templates/auth/login.html")

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(tmpl)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_template_not_found(_make_app):
    """DELETE templates/{name} returns 404 when template doesn't exist."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant_id}/templates/nonexistent.html")

    assert response.status_code == 404


# ===========================================================================
# POST /api/v1/organisations/{org_id}/templates/{template_name}/toggle
# ===========================================================================


@pytest.mark.asyncio
async def test_toggle_template_active_to_inactive(_make_app):
    """POST templates/{name}/toggle flips is_active from True to False."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    tmpl = _make_mock_template(tenant_id, "auth/login.html")
    tmpl.is_active = True

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = tmpl

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant_id}/templates/auth/login.html/toggle"
        )

    assert response.status_code == 200
    assert tmpl.is_active is False
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_toggle_template_inactive_to_active(_make_app):
    """POST templates/{name}/toggle flips is_active from False to True."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    tmpl = _make_mock_template(tenant_id, "auth/login.html")
    tmpl.is_active = False

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = tmpl

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant_id}/templates/auth/login.html/toggle"
        )

    assert response.status_code == 200
    assert tmpl.is_active is True
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_toggle_template_not_found(_make_app):
    """POST templates/{name}/toggle returns 404 when template doesn't exist."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    tmpl_result = MagicMock()
    tmpl_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, tmpl_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant_id}/templates/nonexistent.html/toggle"
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_toggle_template_not_member(_make_app):
    """POST templates/{name}/toggle returns 403 when user is not a member."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant_id}/templates/auth/login.html/toggle"
        )

    assert response.status_code == 403
