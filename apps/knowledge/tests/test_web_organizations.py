# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for web organizations routes (knowledge/routes/web/organizations.py)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import HTMLResponse

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.database import get_db
from knowledge.internal import internal_app
from knowledge.models.enums import (
    OrganizationMemberRole,
    PlanType,
)
from tests.conftest import TEST_TENANT_ID, TEST_USER_ID


def _html_response(status_code=200):
    """Return a real HTMLResponse for template mock return values."""
    return HTMLResponse(content="<html>ok</html>", status_code=status_code)


def _make_mock_tenant(**overrides):
    tenant = MagicMock()
    tenant.id = overrides.get("id", TEST_TENANT_ID)
    tenant.name = overrides.get("name", "Test Org")
    tenant.slug = overrides.get("slug", "test-org")
    tenant.plan = overrides.get("plan", PlanType.FREE)
    tenant.is_active = True
    tenant.can_use_custom_domain = overrides.get("can_use_custom_domain", False)
    tenant.is_enterprise = overrides.get("is_enterprise", False)
    tenant.custom_domain = overrides.get("custom_domain")
    tenant.custom_domain_status = overrides.get("custom_domain_status")
    tenant.custom_domain_error = overrides.get("custom_domain_error")
    return tenant


def _make_mock_member(**overrides):
    member = MagicMock()
    member.id = overrides.get("id", uuid4())
    member.organization_id = overrides.get("organization_id", TEST_TENANT_ID)
    member.user_id = overrides.get("user_id", TEST_USER_ID)
    member.is_owner = overrides.get("is_owner", True)
    member.is_admin = overrides.get("is_admin", True)
    member.role = overrides.get("role", OrganizationMemberRole.OWNER)
    member.can_manage_members = overrides.get("can_manage_members", True)
    member.can_manage_tenant = overrides.get("can_manage_tenant", True)
    return member


def _make_user(**overrides):
    return User(
        id=overrides.get("id", TEST_USER_ID),
        email=overrides.get("email", "test@example.com"),
        name=overrides.get("name", "Test User"),
        nickname=overrides.get("nickname"),
        scopes=overrides.get(
            "scopes",
            [
                "collections:read",
                "collections:write",
                "documents:read",
                "documents:write",
            ],
        ),
    )


def _make_result(scalar_one_or_none=None, scalar=0, scalars_all=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_result())
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _build_auth(tenant=None, member=None, user=None, is_admin=True, is_owner=True):
    t = tenant or _make_mock_tenant()
    m = member or _make_mock_member(is_admin=is_admin, is_owner=is_owner)
    u = user or _make_user()
    ctx = WebAuthContext(user=u, tenant=t, tenant_member=m)
    return ctx


@pytest.fixture
async def web_client(mock_db):
    """Client with admin tenant."""
    auth = _build_auth()

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


@pytest.fixture
async def web_client_no_tenant(mock_db):
    auth = WebAuthContext(user=_make_user(), tenant=None, tenant_member=None)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


@pytest.fixture
async def web_client_non_admin(mock_db):
    member = _make_mock_member(is_admin=False, is_owner=False)
    auth = _build_auth(member=member, is_admin=False, is_owner=False)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


async def test_switch_org_success(web_client, mock_db):
    member = _make_mock_member()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client.post(
        "/organizations/switch",
        data={"organization_id": str(TEST_TENANT_ID)},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "active_tenant_id" in response.headers.get("set-cookie", "")


async def test_switch_org_with_tenant_id_param(web_client, mock_db):
    """Backward compat: tenant_id param works."""
    member = _make_mock_member()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client.post(
        "/organizations/switch",
        data={"tenant_id": str(TEST_TENANT_ID)},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


async def test_switch_org_no_id(web_client, mock_db):
    response = await web_client.post(
        "/organizations/switch",
        data={},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


async def test_switch_org_not_member(web_client, mock_db):
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        "/organizations/switch",
        data={"organization_id": str(uuid4())},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_page_success(mock_billing, mock_templates, web_client, mock_db):
    mock_plan = MagicMock()
    mock_price = MagicMock()
    mock_price.id = "price_123"
    mock_price.interval = "month"
    mock_plan.prices = [mock_price]

    billing = MagicMock()
    billing.is_configured = True
    billing.socket_path = None
    billing.api_url = "http://billing"
    billing.get_plans = AsyncMock(return_value=[mock_plan])
    sub = MagicMock()
    sub.price_id = "price_123"
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[_make_mock_tenant()]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["current_billing_period"] == "monthly"


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_page_yearly(mock_billing, mock_templates, web_client, mock_db):
    mock_plan = MagicMock()
    mock_price = MagicMock()
    mock_price.id = "price_yr"
    mock_price.interval = "year"
    mock_plan.prices = [mock_price]

    billing = MagicMock()
    billing.is_configured = True
    billing.socket_path = None
    billing.api_url = "http://billing"
    billing.get_plans = AsyncMock(return_value=[mock_plan])
    sub = MagicMock()
    sub.price_id = "price_yr"
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[_make_mock_tenant()]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["current_billing_period"] == "yearly"


async def test_pricing_page_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.get("/organizations/pricing", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_page_not_configured(mock_billing, mock_templates, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = False
    billing.socket_path = None
    billing.api_url = ""
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_page_billing_error(mock_billing, mock_templates, web_client, mock_db):
    from knowledge.services.billing import BillingAPIError

    billing = MagicMock()
    billing.is_configured = True
    billing.socket_path = None
    billing.api_url = "http://billing"
    billing.get_plans = AsyncMock(side_effect=BillingAPIError("down"))
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["billing_error"] == "down"


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_page_unexpected_error(mock_billing, mock_templates, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = True
    billing.socket_path = None
    billing.api_url = "http://billing"
    billing.get_plans = AsyncMock(side_effect=RuntimeError("boom"))
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "Unexpected error" in ctx["billing_error"]


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_no_subscription(mock_billing, mock_templates, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = True
    billing.socket_path = None
    billing.api_url = "http://billing"
    billing.get_plans = AsyncMock(return_value=[])
    billing.get_tenant_subscription = AsyncMock(return_value=None)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["current_price_id"] is None


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_subscription_no_price_id(mock_billing, mock_templates, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = True
    billing.socket_path = None
    billing.api_url = "http://billing"
    billing.get_plans = AsyncMock(return_value=[])
    sub = MagicMock()
    sub.price_id = None
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200


@patch(
    "knowledge.routes.web.organizations.checkout_redirect_urls",
    return_value=("http://test/ok", "http://test/ko"),
)
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_checkout_success(mock_billing, mock_settings, web_client, mock_db):

    session = MagicMock()
    session.url = "https://stripe.com/checkout/123"
    billing = MagicMock()
    billing.is_configured = True
    billing.create_checkout_session = AsyncMock(return_value=session)
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/checkout",
        data={"price_id": "price_123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "https://stripe.com/checkout/123"


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_checkout_not_configured(mock_billing, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = False
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/checkout",
        data={"price_id": "price_123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "billing_not_configured" in response.headers["location"]


async def test_checkout_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/checkout",
        data={"price_id": "price_123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


@patch(
    "knowledge.routes.web.organizations.checkout_redirect_urls",
    return_value=("http://test/ok", "http://test/ko"),
)
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_checkout_billing_error(mock_billing, mock_settings, web_client, mock_db):
    from knowledge.services.billing import BillingAPIError

    billing = MagicMock()
    billing.is_configured = True
    billing.create_checkout_session = AsyncMock(side_effect=BillingAPIError("bad"))
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/checkout",
        data={"price_id": "price_123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=" in response.headers["location"]


@patch(
    "knowledge.routes.web.organizations.checkout_redirect_urls",
    return_value=("http://test/ok", "http://test/ko"),
)
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_checkout_personal_workspace(mock_billing, mock_settings, mock_db):
    """Checkout with personal workspace uses user name."""
    tenant = _make_mock_tenant(name="Test User's Workspace")
    user = _make_user(name="Test User")
    auth = _build_auth(tenant=tenant, user=user)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    session = MagicMock()
    session.url = "https://stripe.com/checkout/123"
    billing = MagicMock()
    billing.is_configured = True
    billing.create_checkout_session = AsyncMock(return_value=session)
    mock_billing.return_value = billing

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            "/organizations/checkout",
            data={"price_id": "price_123"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    call_kwargs = billing.create_checkout_session.call_args[1]
    assert call_kwargs["customer_name"] == "Test User"

    internal_app.dependency_overrides.clear()


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_preview_success(mock_billing, web_client, mock_db):
    sub = MagicMock()
    sub.id = "sub_123"

    line_item = MagicMock()
    line_item.description = "Proration"
    line_item.amount = 500
    line_item.display_amount = "$5"

    preview = MagicMock()
    preview.current_plan_name = "Starter"
    preview.new_plan_name = "Pro"
    preview.current_price_amount = 1000
    preview.new_price_amount = 2000
    preview.line_items = [line_item]
    preview.subtotal = 500
    preview.total = 500
    preview.display_total = "$5"
    preview.credit_applied = 500
    preview.display_credit = "$5"
    preview.currency = "usd"

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.preview_upgrade = AsyncMock(return_value=preview)
    mock_billing.return_value = billing

    response = await web_client.get("/organizations/upgrade/preview?price_id=price_456")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["subscription_id"] == "sub_123"


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_preview_not_configured(mock_billing, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = False
    mock_billing.return_value = billing

    response = await web_client.get("/organizations/upgrade/preview?price_id=p1")
    data = response.json()
    assert data["error"] == "Billing not configured"


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_preview_no_subscription(mock_billing, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=None)
    mock_billing.return_value = billing

    response = await web_client.get("/organizations/upgrade/preview?price_id=p1")
    data = response.json()
    assert data["has_subscription"] is False


async def test_upgrade_preview_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.get("/organizations/upgrade/preview?price_id=p1")
    data = response.json()
    assert data["error"] == "No organization selected"


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_preview_billing_error(mock_billing, web_client, mock_db):
    from knowledge.services.billing import BillingAPIError

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(side_effect=BillingAPIError("fail"))
    mock_billing.return_value = billing

    response = await web_client.get("/organizations/upgrade/preview?price_id=p1")
    data = response.json()
    assert data["error"] == "fail"


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_preview_unexpected_error(mock_billing, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(side_effect=RuntimeError("boom"))
    mock_billing.return_value = billing

    response = await web_client.get("/organizations/upgrade/preview?price_id=p1")
    data = response.json()
    assert "Unexpected error" in data["error"]


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_plan_success(mock_billing, web_client, mock_db):
    sub = MagicMock()
    sub.id = "sub_123"
    upgrade_result = MagicMock()
    upgrade_result.success = True

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.upgrade_subscription = AsyncMock(return_value=upgrade_result)
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/upgrade",
        data={"price_id": "price_456"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "upgraded=true" in response.headers["location"]


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_plan_failed(mock_billing, web_client, mock_db):
    sub = MagicMock()
    sub.id = "sub_123"
    upgrade_result = MagicMock()
    upgrade_result.success = False

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.upgrade_subscription = AsyncMock(return_value=upgrade_result)
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/upgrade",
        data={"price_id": "price_456"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "upgrade_failed" in response.headers["location"]


@patch(
    "knowledge.routes.web.organizations.checkout_redirect_urls",
    return_value=("http://test/ok", "http://test/ko"),
)
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_plan_no_subscription_creates_checkout(
    mock_billing, mock_settings, web_client, mock_db
):

    session = MagicMock()
    session.url = "https://stripe.com/checkout"
    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=None)
    billing.create_checkout_session = AsyncMock(return_value=session)
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/upgrade",
        data={"price_id": "price_456"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "https://stripe.com/checkout"


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_plan_not_configured(mock_billing, web_client, mock_db):
    billing = MagicMock()
    billing.is_configured = False
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/upgrade",
        data={"price_id": "price_456"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "billing_not_configured" in response.headers["location"]


async def test_upgrade_plan_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/upgrade",
        data={"price_id": "p1"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_plan_billing_error(mock_billing, web_client, mock_db):
    from knowledge.services.billing import BillingAPIError

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(side_effect=BillingAPIError("err"))
    mock_billing.return_value = billing

    response = await web_client.post(
        "/organizations/upgrade",
        data={"price_id": "p1"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=" in response.headers["location"]


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.QuotaService")
async def test_settings_page(MockQuota, mock_templates, web_client, mock_db):
    usage = MagicMock()
    MockQuota.return_value.get_usage = AsyncMock(return_value=usage)

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/settings")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["usage_stats"] is usage


async def test_settings_page_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.get("/organizations/settings", follow_redirects=False)
    assert response.status_code == 302


@patch("knowledge.routes.web.organizations.templates")
async def test_settings_page_non_admin(mock_templates, web_client_non_admin, mock_db):
    mock_templates.TemplateResponse.return_value = _html_response(403)

    response = await web_client_non_admin.get("/organizations/settings")
    assert response.status_code == 403


async def test_update_settings_success(web_client, mock_db):
    response = await web_client.post(
        "/organizations/settings",
        data={"name": "New Name"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/organizations/settings"


async def test_update_settings_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/settings",
        data={"name": "New"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


@patch("knowledge.routes.web.organizations.templates")
async def test_update_settings_non_admin(mock_templates, web_client_non_admin, mock_db):
    mock_templates.TemplateResponse.return_value = _html_response(403)

    response = await web_client_non_admin.post(
        "/organizations/settings",
        data={"name": "New"},
    )
    assert response.status_code == 403


@pytest.fixture
async def web_client_redirect(mock_db):
    """Client where get_web_auth_context returns a RedirectResponse (unauthenticated)."""
    from starlette.responses import RedirectResponse as StarletteRedirect

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: StarletteRedirect(
        url="/auth/login", status_code=302
    )

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


async def test_switch_organization_auth_redirect(web_client_redirect):
    """Line 87: switch_organization returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/switch",
        data={"organization_id": str(uuid4())},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_pricing_page_auth_redirect(web_client_redirect):
    """Line 129: pricing_page returns auth redirect."""
    response = await web_client_redirect.get("/organizations/pricing", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_checkout_auth_redirect(web_client_redirect):
    """Line 196: checkout returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/checkout",
        data={"price_id": "price_123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_upgrade_preview_auth_redirect(web_client_redirect):
    """Line 254: upgrade_preview returns error dict when auth is RedirectResponse."""
    response = await web_client_redirect.get(
        "/organizations/upgrade/preview?price_id=p1",
        follow_redirects=False,
    )
    # This is a JSON endpoint that returns {"error": "Not authenticated"}
    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "Not authenticated"


async def test_upgrade_plan_auth_redirect(web_client_redirect):
    """Line 317: upgrade_plan returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/upgrade",
        data={"price_id": "price_456"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_organization_settings_auth_redirect(web_client_redirect):
    """Line 389: organization_settings (GET) returns auth redirect."""
    response = await web_client_redirect.get("/organizations/settings", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_update_organization_settings_auth_redirect(web_client_redirect):
    """Line 430: update_organization_settings (POST) returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/settings",
        data={"name": "New Name"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_pricing_page_multiple_plans_match_second(
    mock_billing, mock_templates, web_client, mock_db
):
    """Branch partials 159->158 and 160->159: price not found in first plan,
    match found in second plan after iterating through non-matching prices.
    """
    # First plan with a non-matching price
    plan1 = MagicMock()
    price1 = MagicMock()
    price1.id = "price_other"
    price1.interval = "month"
    plan1.prices = [price1]

    # Second plan with a matching price
    plan2 = MagicMock()
    price2a = MagicMock()
    price2a.id = "price_no_match"
    price2a.interval = "month"
    price2b = MagicMock()
    price2b.id = "price_match"
    price2b.interval = "year"
    plan2.prices = [price2a, price2b]

    billing = MagicMock()
    billing.is_configured = True
    billing.socket_path = None
    billing.api_url = "http://billing"
    billing.get_plans = AsyncMock(return_value=[plan1, plan2])
    sub = MagicMock()
    sub.price_id = "price_match"
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[_make_mock_tenant()]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/pricing")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["current_billing_period"] == "yearly"
    assert ctx["current_price_id"] == "price_match"


@patch(
    "knowledge.routes.web.organizations.checkout_redirect_urls",
    return_value=("http://test/ok", "http://test/ko"),
)
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_upgrade_plan_no_sub_personal_workspace(mock_billing, mock_settings, mock_db):
    """Line 341: upgrade_plan with personal workspace and no subscription uses user name."""
    tenant = _make_mock_tenant(name="Test User's Workspace")
    user = _make_user(name="Test User")
    auth = _build_auth(tenant=tenant, user=user)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    session = MagicMock()
    session.url = "https://stripe.com/checkout/personal"
    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=None)
    billing.create_checkout_session = AsyncMock(return_value=session)
    mock_billing.return_value = billing

    async with AsyncClient(transport=ASGITransport(app=internal_app), base_url="http://test") as ac:
        response = await ac.post(
            "/organizations/upgrade",
            data={"price_id": "price_456"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "https://stripe.com/checkout/personal"
    call_kwargs = billing.create_checkout_session.call_args[1]
    assert call_kwargs["customer_name"] == "Test User"
    internal_app.dependency_overrides.clear()
