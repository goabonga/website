# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations CRUD endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


def _make_mock_tenant(
    tenant_id: uuid.UUID | None = None,
    slug: str = "test-org",
    display_name: str = "Test Organisation",
    is_active: bool = True,
    is_platform: bool = False,
    trust_mode: str = "none",
) -> MagicMock:
    """Build a mock Tenant object."""
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = slug
    tenant.display_name = display_name
    tenant.custom_domain = None
    tenant.is_active = is_active
    tenant.is_platform = is_platform
    tenant.trust_mode = MagicMock()
    tenant.trust_mode.value = trust_mode
    tenant.created_at = datetime.now(UTC)
    tenant.updated_at = datetime.now(UTC)
    return tenant


def _make_mock_membership(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role_name: str = "owner",
    has_star_scope: bool = True,
) -> MagicMock:
    """Build a mock TenantMember with role."""
    member = MagicMock()
    member.tenant_id = tenant_id
    member.user_id = user_id
    member.role_name = role_name

    role = MagicMock()
    role.name = role_name
    member.role = role
    member.custom_role = role

    def has_scope(scope: str) -> bool:
        return bool(has_star_scope)

    member.has_scope = MagicMock(side_effect=has_scope)
    return member


@pytest.fixture
def admin_user():
    """Create a mock admin user with org:* scopes."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    return user


def _override_auth_with_scopes(app, user, scopes):
    """Override auth to inject a user with specific scopes."""

    async def override_auth(request=None):
        # If the dep receives a Request, set scopes on it
        if request is not None:
            request.state.auth_scopes = scopes
            request.state.auth_type = "bearer"
        return user

    # Override get_current_user_bearer
    app.dependency_overrides[get_current_user_bearer] = override_auth

    return scopes


@pytest.fixture
def app_with_admin(admin_user):
    """Create test app with admin auth (org:read, org:write, org:delete)."""
    from auth.main import app as fastapi_app

    scopes = ["org:read", "org:write", "org:delete"]

    async def override_auth():
        return admin_user

    fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth

    # We need to ensure request.state.auth_scopes is set.
    # require_admin_scope reads from request.state, so we patch it to always pass.
    from auth.api.routes.api import deps as api_deps

    original_require_admin_scope = api_deps.require_admin_scope

    def patched_require_admin_scope(scope: str):
        if scope in scopes:

            async def dependency(request, user=None):
                # Accept both positional and keyword
                return admin_user

            return dependency
        return original_require_admin_scope(scope)

    fastapi_app._patched_require = patched_require_admin_scope

    yield fastapi_app, admin_user, scopes

    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(app_with_admin):
    """Create async test client with admin auth."""
    app, admin_user, scopes = app_with_admin

    # Patch require_admin_scope at module level for the organisations router
    with patch("auth.api.routes.api.organisations.require_admin_scope") as mock_ras:

        def make_dep(scope):
            async def dep():
                return admin_user

            return dep

        mock_ras.side_effect = make_dep

        # We need to re-register the routes for the patch to take effect.
        # Instead, let's use a simpler approach: patch at the deps module level.
        pass

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, admin_user


# ---------------------------------------------------------------------------
# Helper to build a client with admin scope patching
# ---------------------------------------------------------------------------


@pytest.fixture
def _make_app():
    """Return a factory that yields (app, user) with the specified scopes."""
    from auth.main import app as fastapi_app

    created = []

    def factory(scopes: list[str], user: MagicMock | None = None):
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
        return fastapi_app, user_, scopes

    yield factory

    for a in created:
        a.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/organisations/ - List (admin)
# ===========================================================================


@pytest.mark.asyncio
async def test_list_organisations_success(_make_app):
    """GET /api/v1/organisations/ returns paginated list for admin."""
    from auth.api.deps import get_db

    app, admin_user, scopes = _make_app(["org:read"])
    tenant = _make_mock_tenant()

    mock_db = AsyncMock()

    # Count query
    count_result = MagicMock()
    count_result.scalar.return_value = 1

    # Select query
    select_result = MagicMock()
    select_scalars = MagicMock()
    select_scalars.all.return_value = [tenant]
    select_result.scalars.return_value = select_scalars

    # Member count query
    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 3

    mock_db.execute = AsyncMock(side_effect=[count_result, select_result, member_count_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.require_admin_scope") as mock_ras:

        def make_dep(scope):
            async def dep():
                return admin_user

            return dep

        mock_ras.side_effect = make_dep

        # Need to refresh the router since require_admin_scope is called at import.
        # Actually, require_admin_scope is called at request time as a Depends, so
        # we need to override differently. Let's override the dependency directly.
        # The real approach: override the specific dependency function returned by
        # require_admin_scope("org:read").
        # Since that's complex, we'll patch at the route level.
        pass

    # Actually the simplest approach: patch token_has_scope to return True
    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/organisations/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 1
    assert data["items"][0]["slug"] == "test-org"
    assert data["items"][0]["member_count"] == 3


@pytest.mark.asyncio
async def test_list_organisations_pagination(_make_app):
    """GET /api/v1/organisations/?page=2&page_size=1 returns correct page."""
    from auth.api.deps import get_db

    app, admin_user, scopes = _make_app(["org:read"])
    tenant = _make_mock_tenant(slug="org-two")

    mock_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 5

    select_result = MagicMock()
    select_scalars = MagicMock()
    select_scalars.all.return_value = [tenant]
    select_result.scalars.return_value = select_scalars

    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 1

    mock_db.execute = AsyncMock(side_effect=[count_result, select_result, member_count_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/organisations/?page=2&page_size=1")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert data["page"] == 2
    assert data["page_size"] == 1


@pytest.mark.asyncio
async def test_list_organisations_forbidden(_make_app):
    """GET /api/v1/organisations/ without org:read scope returns 403."""
    from auth.api.deps import get_db

    app, user, _ = _make_app([])

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    # token_has_scope returns False -> require_admin_scope raises 403
    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/organisations/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_organisations_unauthenticated():
    """GET /api/v1/organisations/ without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/organisations/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# POST /api/v1/organisations/ - Create (admin)
# ===========================================================================


@pytest.mark.asyncio
async def test_create_organisation_success(_make_app):
    """POST /api/v1/organisations/ creates org and returns 201."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])
    tenant_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    # Slug uniqueness check - no existing
    slug_check = MagicMock()
    slug_check.scalar_one_or_none.return_value = None

    # Member count after creation
    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 0

    mock_db.execute = AsyncMock(side_effect=[slug_check, member_count_result])

    added_objects: list = []

    def capture_add(obj):
        added_objects.append(obj)

    mock_db.add = MagicMock(side_effect=capture_add)

    now = datetime.now(UTC)

    async def mock_flush():
        for obj in added_objects:
            if hasattr(obj, "slug") and not hasattr(obj, "_id_set"):
                obj.id = tenant_id
                obj.created_at = now
                obj.updated_at = now
                obj.is_active = True
                obj.is_platform = False
                obj.custom_domain = None
                obj.trust_mode = MagicMock()
                obj.trust_mode.value = "none"
                obj._id_set = True

    mock_db.flush = AsyncMock(side_effect=mock_flush)

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
        patch("auth.api.routes.api.organisations.tenant_role_service") as mock_role_svc,
    ):
        mock_role_svc.create_default_roles = AsyncMock(return_value=[])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/organisations/",
                json={
                    "slug": "new-org",
                    "display_name": "New Organisation",
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == str(tenant_id)
    assert data["slug"] == "new-org"
    assert data["display_name"] == "New Organisation"
    assert data["member_count"] == 0
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_organisation_duplicate_slug(_make_app):
    """POST /api/v1/organisations/ with duplicate slug returns 409."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])

    mock_db = AsyncMock()
    slug_check = MagicMock()
    slug_check.scalar_one_or_none.return_value = MagicMock()  # exists
    mock_db.execute = AsyncMock(return_value=slug_check)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/organisations/",
                json={
                    "slug": "existing-org",
                    "display_name": "Dup Org",
                },
            )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_organisation_invalid_slug(_make_app):
    """POST /api/v1/organisations/ with invalid slug returns 422."""
    app, _, _ = _make_app(["org:write"])

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/organisations/",
                json={
                    "slug": "INVALID SLUG!",
                    "display_name": "Bad Org",
                },
            )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_organisation_forbidden(_make_app):
    """POST /api/v1/organisations/ without org:write scope returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/organisations/",
                json={
                    "slug": "new-org",
                    "display_name": "New Org",
                },
            )

    assert response.status_code == 403


# ===========================================================================
# GET /api/v1/organisations/{org_id} - Get one
# ===========================================================================


@pytest.mark.asyncio
async def test_get_organisation_admin(_make_app):
    """GET /api/v1/organisations/{id} with admin scope returns org."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:read"])
    tenant = _make_mock_tenant()

    mock_db = AsyncMock()

    # Tenant query
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    # Member count
    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 5

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_count_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "test-org"
    assert data["member_count"] == 5


@pytest.mark.asyncio
async def test_get_organisation_member(_make_app):
    """GET /api/v1/organisations/{id} as org member returns org."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True

    app, user, _ = _make_app([], user=user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    # Tenant query
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    # Membership query
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    # Member count
    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 2

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, member_count_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    # Set auth_scopes on request state - token_has_scope returns False (no admin)
    with patch(
        "auth.api.routes.api.organisations.token_has_scope",
        return_value=False,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "test-org"
    assert data["member_count"] == 2


@pytest.mark.asyncio
async def test_get_organisation_not_found(_make_app):
    """GET /api/v1/organisations/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:read"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_organisation_non_member_forbidden(_make_app):
    """GET /api/v1/organisations/{id} as non-member returns 403."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True

    app, user, _ = _make_app([], user=user)
    tenant = _make_mock_tenant()

    mock_db = AsyncMock()

    # Tenant query
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    # Membership query - not a member
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(
        "auth.api.routes.api.organisations.token_has_scope",
        return_value=False,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}")

    assert response.status_code == 403


# ===========================================================================
# PATCH /api/v1/organisations/{org_id} - Update
# ===========================================================================


@pytest.mark.asyncio
async def test_update_organisation_admin(_make_app):
    """PATCH /api/v1/organisations/{id} with admin scope updates org."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])
    tenant = _make_mock_tenant()

    mock_db = AsyncMock()

    # Tenant query
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    # Member count
    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 1

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_count_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}",
                json={"display_name": "Updated Name"},
            )

    assert response.status_code == 200
    assert tenant.display_name == "Updated Name"


@pytest.mark.asyncio
async def test_update_organisation_owner(_make_app):
    """PATCH /api/v1/organisations/{id} as owner updates org."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True

    app, user, _ = _make_app([], user=user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id, has_star_scope=True)

    mock_db = AsyncMock()

    # Tenant query
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    # Membership query (with selectinload)
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    # Member count
    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 2

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, member_count_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(
            "auth.api.routes.api.organisations.token_has_scope",
            return_value=False,
        ),
        patch("auth.api.routes.api.organisations.tenant_role_service") as mock_role_svc,
    ):
        mock_role_svc.is_owner.return_value = True

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}",
                json={
                    "display_name": "Owner Updated",
                    "is_active": False,
                },
            )

    assert response.status_code == 200
    assert tenant.display_name == "Owner Updated"
    assert tenant.is_active is False


@pytest.mark.asyncio
async def test_update_organisation_not_found(_make_app):
    """PATCH /api/v1/organisations/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{uuid.uuid4()}",
                json={"display_name": "Nope"},
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_organisation_non_owner_forbidden(_make_app):
    """PATCH /api/v1/organisations/{id} as non-owner non-admin returns 403."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True

    app, user, _ = _make_app([], user=user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id, role_name="member", has_star_scope=False)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(
            "auth.api.routes.api.organisations.token_has_scope",
            return_value=False,
        ),
        patch("auth.api.routes.api.organisations.tenant_role_service") as mock_role_svc,
    ):
        mock_role_svc.is_owner.return_value = False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}",
                json={"display_name": "Forbidden"},
            )

    assert response.status_code == 403


# ===========================================================================
# DELETE /api/v1/organisations/{org_id} - Delete (admin)
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_organisation_success(_make_app):
    """DELETE /api/v1/organisations/{id} with admin scope returns 204."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:delete"])
    tenant = _make_mock_tenant()

    mock_db = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    mock_db.execute = AsyncMock(return_value=tenant_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant.id}")

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(tenant)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_organisation_not_found(_make_app):
    """DELETE /api/v1/organisations/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:delete"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_platform_tenant_forbidden(_make_app):
    """DELETE /api/v1/organisations/{id} on platform tenant returns 400."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:delete"])
    tenant = _make_mock_tenant(is_platform=True)

    mock_db = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    mock_db.execute = AsyncMock(return_value=tenant_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant.id}")

    assert response.status_code == 400
    assert "platform" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_organisation_forbidden(_make_app):
    """DELETE /api/v1/organisations/{id} without org:delete returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{uuid.uuid4()}")

    assert response.status_code == 403


# ===========================================================================
# POST /api/v1/organisations/{org_id}/enable - Enable (admin)
# ===========================================================================


@pytest.mark.asyncio
async def test_enable_organisation_success(_make_app):
    """POST /api/v1/organisations/{id}/enable sets is_active to True."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])
    tenant = _make_mock_tenant(is_active=False)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 2

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_count_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/organisations/{tenant.id}/enable")

    assert response.status_code == 200
    assert tenant.is_active is True
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_enable_organisation_not_found(_make_app):
    """POST /api/v1/organisations/{id}/enable returns 404 for unknown org."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/organisations/{uuid.uuid4()}/enable")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_enable_organisation_forbidden(_make_app):
    """POST /api/v1/organisations/{id}/enable without org:write returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/organisations/{uuid.uuid4()}/enable")

    assert response.status_code == 403


# ===========================================================================
# POST /api/v1/organisations/{org_id}/disable - Disable (admin)
# ===========================================================================


@pytest.mark.asyncio
async def test_disable_organisation_success(_make_app):
    """POST /api/v1/organisations/{id}/disable sets is_active to False."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])
    tenant = _make_mock_tenant(is_active=True)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant

    member_count_result = MagicMock()
    member_count_result.scalar.return_value = 3

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_count_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/organisations/{tenant.id}/disable")

    assert response.status_code == 200
    assert tenant.is_active is False
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_disable_organisation_not_found(_make_app):
    """POST /api/v1/organisations/{id}/disable returns 404 for unknown org."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/organisations/{uuid.uuid4()}/disable")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_disable_platform_tenant_forbidden(_make_app):
    """POST /api/v1/organisations/{id}/disable on platform tenant returns 400."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["org:write"])
    tenant = _make_mock_tenant(is_platform=True)

    mock_db = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    mock_db.execute = AsyncMock(return_value=tenant_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/organisations/{tenant.id}/disable")

    assert response.status_code == 400
    assert "platform" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_disable_organisation_forbidden(_make_app):
    """POST /api/v1/organisations/{id}/disable without org:write returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/organisations/{uuid.uuid4()}/disable")

    assert response.status_code == 403
