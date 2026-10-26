# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for web home routes (knowledge/routes/web/home.py)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.responses import RedirectResponse
from httpx import ASGITransport, AsyncClient
from starlette.responses import HTMLResponse

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.database import get_db
from knowledge.internal import internal_app
from knowledge.models.enums import PlanType
from tests.conftest import TEST_TENANT_ID, TEST_USER_ID


def _html_response(status_code=200):
    """Return a real HTMLResponse for template mock return values."""
    return HTMLResponse(content="<html>ok</html>", status_code=status_code)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_tenant(**overrides):
    tenant = MagicMock()
    tenant.id = overrides.get("id", TEST_TENANT_ID)
    tenant.name = overrides.get("name", "Test Org")
    tenant.slug = overrides.get("slug", "test-org")
    tenant.plan = overrides.get("plan", PlanType.FREE)
    tenant.is_active = True
    return tenant


def _make_mock_member(**overrides):
    member = MagicMock()
    member.id = overrides.get("id", uuid4())
    member.organization_id = overrides.get("organization_id", TEST_TENANT_ID)
    member.user_id = overrides.get("user_id", TEST_USER_ID)
    member.is_owner = True
    member.is_admin = True
    return member


def _make_user():
    return User(
        id=TEST_USER_ID,
        email="test@example.com",
        name="Test User",
        scopes=["collections:read", "collections:write", "documents:read", "documents:write"],
    )


def _make_result(scalar_one_or_none=None, scalar=0, scalars_all=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_result())
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def auth_context_with_tenant():
    return WebAuthContext(
        user=_make_user(),
        tenant=_make_mock_tenant(),
        tenant_member=_make_mock_member(),
    )


@pytest.fixture
def auth_context_no_tenant():
    return WebAuthContext(
        user=_make_user(),
        tenant=None,
        tenant_member=None,
    )


@pytest.fixture
async def web_client(mock_db, auth_context_with_tenant):
    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth_context_with_tenant

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


@pytest.fixture
async def web_client_no_tenant(mock_db, auth_context_no_tenant):
    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth_context_no_tenant

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


@pytest.fixture
async def web_client_no_auth(mock_db):
    """Client with no auth override (for public pages)."""

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# home (/)
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.home.templates")
@patch("knowledge.auth.dependencies.get_token_from_cookie", new_callable=AsyncMock)
async def test_home_no_token(mock_get_token, mock_templates, web_client_no_auth):
    """Home page without token shows landing page."""
    mock_get_token.return_value = None
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_auth.get("/")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "pages/home.html"
    ctx = call_args[0][2]
    assert ctx["user"] is None


@patch("knowledge.auth.dependencies.get_token_from_cookie", new_callable=AsyncMock)
async def test_home_with_token(mock_get_token, web_client_no_auth):
    """Home page with token redirects to dashboard."""
    mock_get_token.return_value = "some-jwt-token"

    response = await web_client_no_auth.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


# ---------------------------------------------------------------------------
# legal, privacy, terms
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.home.templates")
async def test_legal_page(mock_templates, web_client_no_auth):
    mock_templates.TemplateResponse.return_value = _html_response()
    response = await web_client_no_auth.get("/legal")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "pages/legal.html"


@patch("knowledge.routes.web.home.templates")
async def test_privacy_page(mock_templates, web_client_no_auth):
    mock_templates.TemplateResponse.return_value = _html_response()
    response = await web_client_no_auth.get("/privacy")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "pages/privacy.html"


@patch("knowledge.routes.web.home.templates")
async def test_terms_page(mock_templates, web_client_no_auth):
    mock_templates.TemplateResponse.return_value = _html_response()
    response = await web_client_no_auth.get("/terms")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "pages/terms.html"


# ---------------------------------------------------------------------------
# pricing (public)
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.home.templates")
@patch("knowledge.routes.web.home.get_billing_client")
async def test_pricing_page_with_plans(mock_billing, mock_templates, web_client_no_auth):
    billing_client = MagicMock()
    billing_client.is_configured = True
    billing_client.get_plans = AsyncMock(return_value=[MagicMock(name="Free")])
    mock_billing.return_value = billing_client
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_auth.get("/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert len(ctx["plans"]) == 1
    assert ctx["billing_error"] is None


@patch("knowledge.routes.web.home.templates")
@patch("knowledge.routes.web.home.get_billing_client")
async def test_pricing_page_not_configured(mock_billing, mock_templates, web_client_no_auth):
    billing_client = MagicMock()
    billing_client.is_configured = False
    mock_billing.return_value = billing_client
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_auth.get("/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["plans"] == []


@patch("knowledge.routes.web.home.templates")
@patch("knowledge.routes.web.home.get_billing_client")
async def test_pricing_page_billing_api_error(mock_billing, mock_templates, web_client_no_auth):
    from knowledge.services.billing import BillingAPIError

    billing_client = MagicMock()
    billing_client.is_configured = True
    billing_client.get_plans = AsyncMock(side_effect=BillingAPIError("API down"))
    mock_billing.return_value = billing_client
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_auth.get("/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["billing_error"] == "API down"


@patch("knowledge.routes.web.home.templates")
@patch("knowledge.routes.web.home.get_billing_client")
async def test_pricing_page_unexpected_error(mock_billing, mock_templates, web_client_no_auth):
    billing_client = MagicMock()
    billing_client.is_configured = True
    billing_client.get_plans = AsyncMock(side_effect=RuntimeError("boom"))
    mock_billing.return_value = billing_client
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_auth.get("/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "Unexpected error" in ctx["billing_error"]


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.home.templates")
@patch("knowledge.routes.web.home.QuotaService")
async def test_dashboard_with_tenant(MockQuotaService, mock_templates, web_client, mock_db):
    """Dashboard with tenant shows stats."""
    usage_stats = MagicMock()
    usage_stats.storage_bytes.current = 2048
    quota_instance = MockQuotaService.return_value
    quota_instance.get_usage = AsyncMock(return_value=usage_stats)

    coll = MagicMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
            _make_result(scalar=5),  # collections count
            _make_result(scalar=50),  # documents count
            _make_result(scalars_all=[coll]),  # recent collections
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/dashboard")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "pages/dashboard.html"
    ctx = call_args[0][2]
    assert ctx["active_section"] == "dashboard"
    assert ctx["usage_stats"] is usage_stats
    assert ctx["storage_used"] == 2048


@patch("knowledge.routes.web.home.templates")
async def test_dashboard_no_tenant(mock_templates, web_client_no_tenant, mock_db):
    """Dashboard without tenant shows zeroed stats."""
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_tenant.get("/dashboard")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["collections_count"] == 0
    assert ctx["documents_count"] == 0
    assert ctx["storage_used"] == 0
    assert ctx["usage_stats"] is None


# ---------------------------------------------------------------------------
# dashboard auth redirect (line 105)
# ---------------------------------------------------------------------------


@pytest.fixture
async def web_client_redirect(mock_db):
    """Client where get_web_auth_context returns a RedirectResponse."""
    redirect = RedirectResponse(url="/auth/login", status_code=302)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: redirect

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


async def test_dashboard_auth_redirect(web_client_redirect):
    """Dashboard returns redirect when auth is RedirectResponse (line 105)."""
    response = await web_client_redirect.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]
