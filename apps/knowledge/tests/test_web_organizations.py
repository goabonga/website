# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for web organizations routes (knowledge/routes/web/organizations.py)."""

from datetime import UTC, datetime, timedelta
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
    CustomDomainStatus,
    InvitationStatus,
    OrganizationMemberRole,
    PlanType,
)
from knowledge.models.workspace_deletion_request import (
    DeletionRequestStatus,
    WorkspaceDeletionRequest,
)
from knowledge.services.custom_domain import CustomDomainError, RegisteredDomain
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
    tenant.can_use_custom_domain = overrides.get("can_use_custom_domain", False)
    tenant.is_enterprise = overrides.get("is_enterprise", False)
    tenant.custom_domain = overrides.get("custom_domain")
    tenant.custom_domain_status = overrides.get("custom_domain_status")
    tenant.custom_domain_error = overrides.get("custom_domain_error")
    tenant.custom_domain_service_id = overrides.get("custom_domain_service_id")
    tenant.custom_domain_cname_target = overrides.get("custom_domain_cname_target")
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


def _make_deletion_request(**overrides):
    dr = MagicMock()
    dr.id = overrides.get("id", uuid4())
    dr.organization_id = overrides.get("organization_id", TEST_TENANT_ID)
    dr.requested_by = overrides.get("requested_by", TEST_USER_ID)
    dr.email = overrides.get("email", "test@example.com")
    dr.token = overrides.get("token", "test-token-123")
    dr.cancel_token = overrides.get("cancel_token", "cancel-token-123")
    dr.status = overrides.get("status", DeletionRequestStatus.PENDING)
    dr.expires_at = overrides.get("expires_at", datetime.now(UTC) + timedelta(hours=24))
    dr.confirmed_at = overrides.get("confirmed_at")
    dr.scheduled_deletion_at = overrides.get("scheduled_deletion_at")
    dr.subscription_cancelled = overrides.get("subscription_cancelled", False)
    dr.is_expired = overrides.get("is_expired", False)
    dr.is_valid = overrides.get("is_valid", True)
    dr.is_pending = overrides.get("is_pending", True)
    dr.confirm = MagicMock()
    dr.cancel = MagicMock()
    dr.mark_expired = MagicMock()
    dr.schedule = MagicMock()
    return dr


def _make_invitation(**overrides):
    inv = MagicMock()
    inv.id = overrides.get("id", uuid4())
    inv.organization_id = overrides.get("organization_id", TEST_TENANT_ID)
    inv.email = overrides.get("email", "invited@example.com")
    inv.role = overrides.get("role", OrganizationMemberRole.MEMBER)
    inv.token = overrides.get("token", "inv-token-123")
    inv.status = overrides.get("status", InvitationStatus.PENDING)
    inv.invited_by = overrides.get("invited_by", TEST_USER_ID)
    inv.expires_at = overrides.get("expires_at", datetime.now(UTC) + timedelta(days=7))
    inv.accepted_at = overrides.get("accepted_at")
    return inv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


@pytest.fixture
async def web_client_admin_not_owner(mock_db):
    member = _make_mock_member(is_admin=True, is_owner=False)
    auth = _build_auth(member=member, is_admin=True, is_owner=False)

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


# ===========================================================================
# switch_organization
# ===========================================================================


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


# ===========================================================================
# pricing_page
# ===========================================================================


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


# ===========================================================================
# checkout
# ===========================================================================


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


# ===========================================================================
# upgrade_preview
# ===========================================================================


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


# ===========================================================================
# upgrade_plan
# ===========================================================================


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


# ===========================================================================
# organization_settings (GET)
# ===========================================================================


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


# ===========================================================================
# update_organization_settings (POST)
# ===========================================================================


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


# ===========================================================================
# delete_organization (POST)
# ===========================================================================


@patch("knowledge.routes.web.organizations.send_workspace_deletion_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.templates")
async def test_delete_org_request(mock_templates, mock_settings, mock_email, web_client, mock_db):
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    # No existing pending requests
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # existing requests
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    with (
        patch.object(WorkspaceDeletionRequest, "generate_token", return_value="tok123"),
        patch.object(
            WorkspaceDeletionRequest,
            "default_expiry",
            return_value=datetime.now(UTC) + timedelta(hours=24),
        ),
    ):
        response = await web_client.post(
            "/organizations/delete",
            data={"confirmation_name": "Test Org"},
        )
    assert response.status_code == 200
    mock_email.delay.assert_called_once()


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.QuotaService")
async def test_delete_org_wrong_name(MockQuota, mock_templates, web_client, mock_db):
    MockQuota.return_value.get_usage = AsyncMock(return_value=MagicMock())

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post(
        "/organizations/delete",
        data={"confirmation_name": "Wrong Name"},
    )
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "does not match" in ctx["delete_error"]


async def test_delete_org_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/delete",
        data={"confirmation_name": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 302


@patch("knowledge.routes.web.organizations.templates")
async def test_delete_org_not_owner(mock_templates, web_client_admin_not_owner, mock_db):
    mock_templates.TemplateResponse.return_value = _html_response(403)

    response = await web_client_admin_not_owner.post(
        "/organizations/delete",
        data={"confirmation_name": "Test Org"},
    )
    assert response.status_code == 403


# ===========================================================================
# confirm_deletion_page (GET)
# ===========================================================================


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_success(mock_templates, web_client, mock_db):
    dr = _make_deletion_request(status=DeletionRequestStatus.PENDING, is_expired=False)
    org = _make_mock_tenant()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
            _make_result(scalar_one_or_none=dr),  # deletion request
            _make_result(scalar_one_or_none=org),  # organization
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/test-token-123")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_confirm.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_not_found(mock_templates, web_client, mock_db):
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # tenants
            _make_result(scalar_one_or_none=None),  # no request
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/bad-token")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_expired(mock_templates, web_client, mock_db):
    dr = _make_deletion_request(
        status=DeletionRequestStatus.PENDING,
        is_expired=True,
    )

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/tok")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"
    dr.mark_expired.assert_called_once()


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_already_confirmed(mock_templates, web_client, mock_db):
    dr = _make_deletion_request(
        status=DeletionRequestStatus.CONFIRMED,
        is_expired=False,
    )

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/tok")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_cancelled(mock_templates, web_client, mock_db):
    dr = _make_deletion_request(status=DeletionRequestStatus.CANCELLED, is_expired=False)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/tok")
    assert response.status_code == 200


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_expired_status(mock_templates, web_client, mock_db):
    dr = _make_deletion_request(status=DeletionRequestStatus.EXPIRED, is_expired=False)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/tok")
    assert response.status_code == 200


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_org_not_found(mock_templates, web_client, mock_db):
    dr = _make_deletion_request(status=DeletionRequestStatus.PENDING, is_expired=False)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=None),  # org not found
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/tok")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"


# ===========================================================================
# execute_deletion (POST)
# ===========================================================================


@patch("knowledge.routes.web.organizations.send_workspace_deleted_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_immediate(
    mock_billing, mock_settings, mock_email, web_client, mock_db
):
    """No subscription -> immediate deletion, user has remaining workspaces."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    billing = MagicMock()
    billing.is_configured = False
    mock_billing.return_value = billing

    dr = _make_deletion_request(is_valid=True, is_expired=False)
    org = _make_mock_tenant()
    remaining_member = _make_mock_member()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
            _make_result(scalar_one_or_none=dr),  # deletion request
            _make_result(scalar_one_or_none=org),  # organization
            _make_result(scalar_one_or_none=remaining_member),  # has remaining workspaces
        ]
    )

    response = await web_client.post(
        "/organizations/delete/confirm/test-token-123",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/dashboard?deleted=true" in response.headers["location"]
    dr.confirm.assert_called_once()
    mock_db.delete.assert_called_once_with(org)
    mock_email.delay.assert_called_once()


@patch("knowledge.routes.web.organizations.send_workspace_deleted_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_no_remaining_workspaces(
    mock_billing, mock_settings, mock_email, web_client, mock_db
):
    """No remaining workspaces -> redirect to logout."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    billing = MagicMock()
    billing.is_configured = False
    mock_billing.return_value = billing

    dr = _make_deletion_request(is_valid=True, is_expired=False)
    org = _make_mock_tenant()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # tenants
            _make_result(scalar_one_or_none=dr),  # deletion request
            _make_result(scalar_one_or_none=org),  # organization
            _make_result(scalar_one_or_none=None),  # no remaining workspaces
        ]
    )

    response = await web_client.post(
        "/organizations/delete/confirm/test-token-123",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/logout" in response.headers["location"]


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_not_found(mock_billing, mock_templates, web_client, mock_db):
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=None),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post("/organizations/delete/confirm/bad-token")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_invalid(mock_billing, mock_templates, web_client, mock_db):
    dr = _make_deletion_request(
        is_valid=False, is_expired=True, status=DeletionRequestStatus.PENDING
    )

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post("/organizations/delete/confirm/tok")
    assert response.status_code == 200
    dr.mark_expired.assert_called_once()


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_invalid_not_expired(
    mock_billing, mock_templates, web_client, mock_db
):
    dr = _make_deletion_request(is_valid=False, is_expired=False)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post("/organizations/delete/confirm/tok")
    assert response.status_code == 200


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_org_not_found(mock_billing, mock_templates, web_client, mock_db):
    dr = _make_deletion_request(is_valid=True)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=None),  # org not found
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post("/organizations/delete/confirm/tok")
    assert response.status_code == 200
    dr.cancel.assert_called_once()


@patch("knowledge.routes.web.organizations.send_workspace_deletion_scheduled_email")
@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_scheduled(
    mock_billing, mock_templates, mock_sched_email, web_client, mock_db
):
    """Active subscription -> schedule deletion for end of period."""
    sub = MagicMock()
    sub.id = "sub_123"
    sub.status = "active"
    sub.current_period_end = datetime.now(UTC) + timedelta(days=30)

    cancel_result = MagicMock()
    cancel_result.success = True

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.cancel_subscription = AsyncMock(return_value=cancel_result)
    mock_billing.return_value = billing

    dr = _make_deletion_request(is_valid=True)
    org = _make_mock_tenant()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post("/organizations/delete/confirm/tok")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_scheduled.html"
    dr.schedule.assert_called_once()
    mock_sched_email.delay.assert_called_once()


@patch("knowledge.routes.web.organizations.send_workspace_deleted_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_cancel_failed(
    mock_billing, mock_settings, mock_email, web_client, mock_db
):
    """Cancel subscription fails -> proceed with immediate deletion."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    sub = MagicMock()
    sub.id = "sub_123"
    sub.status = "active"
    sub.current_period_end = datetime.now(UTC) + timedelta(days=30)

    cancel_result = MagicMock()
    cancel_result.success = False
    cancel_result.error = "Failed"

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.cancel_subscription = AsyncMock(return_value=cancel_result)
    mock_billing.return_value = billing

    dr = _make_deletion_request(is_valid=True)
    org = _make_mock_tenant()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
            _make_result(scalar_one_or_none=None),  # no remaining
        ]
    )

    response = await web_client.post(
        "/organizations/delete/confirm/tok",
        follow_redirects=False,
    )
    assert response.status_code == 302
    dr.confirm.assert_called_once()
    mock_db.delete.assert_called_once_with(org)


@patch("knowledge.routes.web.organizations.send_workspace_deleted_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_subscription_expired(
    mock_billing, mock_settings, mock_email, web_client, mock_db
):
    """Subscription period already ended -> immediate deletion."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    sub = MagicMock()
    sub.id = "sub_123"
    sub.status = "active"
    sub.current_period_end = datetime.now(UTC) - timedelta(days=1)  # already past

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    mock_billing.return_value = billing

    dr = _make_deletion_request(is_valid=True)
    org = _make_mock_tenant()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
            _make_result(scalar_one_or_none=None),
        ]
    )

    response = await web_client.post(
        "/organizations/delete/confirm/tok",
        follow_redirects=False,
    )
    assert response.status_code == 302
    dr.confirm.assert_called_once()


@patch("knowledge.routes.web.organizations.send_workspace_deleted_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_sub_fetch_error(
    mock_billing, mock_settings, mock_email, web_client, mock_db
):
    """Error fetching subscription -> still delete."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(side_effect=RuntimeError("err"))
    mock_billing.return_value = billing

    dr = _make_deletion_request(is_valid=True)
    org = _make_mock_tenant()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
            _make_result(scalar_one_or_none=None),
        ]
    )

    response = await web_client.post(
        "/organizations/delete/confirm/tok",
        follow_redirects=False,
    )
    assert response.status_code == 302
    dr.confirm.assert_called_once()


@patch("knowledge.routes.web.organizations.send_workspace_deleted_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_execute_deletion_trialing_subscription(
    mock_billing, mock_settings, mock_email, web_client, mock_db
):
    """Trialing subscription also triggers scheduled deletion."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    sub = MagicMock()
    sub.id = "sub_t"
    sub.status = "trialing"
    sub.current_period_end = datetime.now(UTC) + timedelta(days=14)

    cancel_result = MagicMock()
    cancel_result.success = True

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.cancel_subscription = AsyncMock(return_value=cancel_result)
    mock_billing.return_value = billing

    dr = _make_deletion_request(is_valid=True)
    org = _make_mock_tenant()

    # Need to patch templates for the scheduled response
    with (
        patch("knowledge.routes.web.organizations.templates") as mock_templates,
        patch("knowledge.routes.web.organizations.send_workspace_deletion_scheduled_email"),
    ):
        mock_templates.TemplateResponse.return_value = _html_response()
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_result(scalars_all=[]),
                _make_result(scalar_one_or_none=dr),
                _make_result(scalar_one_or_none=org),
            ]
        )

        response = await web_client.post("/organizations/delete/confirm/tok")
        assert response.status_code == 200
        dr.schedule.assert_called_once()


# ===========================================================================
# cancel_scheduled_deletion
# ===========================================================================


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_cancel_scheduled_deletion_success(mock_billing, mock_templates, web_client, mock_db):
    dr = _make_deletion_request(
        status=DeletionRequestStatus.SCHEDULED,
        subscription_cancelled=True,
    )
    org = _make_mock_tenant()
    sub = MagicMock()
    sub.id = "sub_123"
    sub.cancel_at_period_end = True

    reactivate = MagicMock()
    reactivate.success = True

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.reactivate_subscription = AsyncMock(return_value=reactivate)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/cancel-token-123")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_cancelled.html"
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["subscription_reactivated"] is True
    dr.cancel.assert_called_once()


@patch("knowledge.routes.web.organizations.templates")
async def test_cancel_scheduled_deletion_not_found(mock_templates, web_client, mock_db):
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=None),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/bad")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_cancel_scheduled_deletion_wrong_status(mock_templates, web_client, mock_db):
    """Not SCHEDULED status returns error for each status."""
    for status in [
        DeletionRequestStatus.CONFIRMED,
        DeletionRequestStatus.CANCELLED,
        DeletionRequestStatus.PENDING,
        DeletionRequestStatus.EXPIRED,
    ]:
        dr = _make_deletion_request(status=status)

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_result(scalars_all=[]),
                _make_result(scalar_one_or_none=dr),
            ]
        )
        mock_templates.TemplateResponse.return_value = _html_response()

        response = await web_client.get("/organizations/delete/cancel/tok")
        assert response.status_code == 200
        assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_cancel_scheduled_deletion_org_not_found(mock_templates, web_client, mock_db):
    dr = _make_deletion_request(status=DeletionRequestStatus.SCHEDULED)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=None),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/tok")
    assert response.status_code == 200
    dr.cancel.assert_called_once()


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_cancel_scheduled_reactivation_failed(
    mock_billing, mock_templates, web_client, mock_db
):
    dr = _make_deletion_request(
        status=DeletionRequestStatus.SCHEDULED,
        subscription_cancelled=True,
    )
    org = _make_mock_tenant()
    sub = MagicMock()
    sub.id = "sub_123"
    sub.cancel_at_period_end = True

    reactivate = MagicMock()
    reactivate.success = False
    reactivate.error = "fail"

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    billing.reactivate_subscription = AsyncMock(return_value=reactivate)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/tok")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["subscription_reactivated"] is False


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_cancel_scheduled_reactivation_exception(
    mock_billing, mock_templates, web_client, mock_db
):
    dr = _make_deletion_request(
        status=DeletionRequestStatus.SCHEDULED,
        subscription_cancelled=True,
    )
    org = _make_mock_tenant()

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(side_effect=RuntimeError("err"))
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/tok")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["subscription_reactivated"] is False


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_cancel_scheduled_no_sub_cancelled(mock_billing, mock_templates, web_client, mock_db):
    """subscription_cancelled is False -> skip reactivation."""
    dr = _make_deletion_request(
        status=DeletionRequestStatus.SCHEDULED,
        subscription_cancelled=False,
    )
    org = _make_mock_tenant()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/tok")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["subscription_reactivated"] is False


# ===========================================================================
# organization_members
# ===========================================================================


@patch("knowledge.routes.web.organizations.templates")
async def test_members_page(mock_templates, web_client, mock_db):
    member = _make_mock_member()
    inv = _make_invitation()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[member]),  # members
            _make_result(scalars_all=[inv]),  # invitations
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/members")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/members.html"


async def test_members_page_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.get("/organizations/members", follow_redirects=False)
    assert response.status_code == 302


@patch("knowledge.routes.web.organizations.templates")
async def test_members_page_non_admin(mock_templates, web_client_non_admin, mock_db):
    mock_templates.TemplateResponse.return_value = _html_response(403)

    response = await web_client_non_admin.get("/organizations/members")
    assert response.status_code == 403


# ===========================================================================
# invite_form
# ===========================================================================


@patch("knowledge.routes.web.organizations.templates")
async def test_invite_form(mock_templates, web_client, mock_db):
    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/invite")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/invite.html"


async def test_invite_form_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.get("/organizations/invite", follow_redirects=False)
    assert response.status_code == 302


@patch("knowledge.routes.web.organizations.templates")
async def test_invite_form_non_admin(mock_templates, web_client_non_admin, mock_db):
    mock_templates.TemplateResponse.return_value = _html_response(403)
    response = await web_client_non_admin.get("/organizations/invite")
    assert response.status_code == 403


# ===========================================================================
# create_invitation
# ===========================================================================


@patch("knowledge.tasks.send_workspace_invitation_email")
@patch("knowledge.routes.web.organizations.get_settings")
async def test_create_invitation_success(mock_settings, mock_email, web_client, mock_db):
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        "/organizations/invite",
        data={"email": "new@example.com", "role": "member"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/organizations/members"


@patch("knowledge.routes.web.organizations.templates")
async def test_create_invitation_already_pending(mock_templates, web_client, mock_db):
    existing = _make_invitation(email="dup@example.com")
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=existing),  # already exists
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post(
        "/organizations/invite",
        data={"email": "dup@example.com", "role": "member"},
    )
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "already pending" in ctx["error"]


async def test_create_invitation_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/invite",
        data={"email": "x@x.com", "role": "member"},
        follow_redirects=False,
    )
    assert response.status_code == 302


@patch("knowledge.routes.web.organizations.templates")
async def test_create_invitation_non_admin(mock_templates, web_client_non_admin, mock_db):
    mock_templates.TemplateResponse.return_value = _html_response(403)
    response = await web_client_non_admin.post(
        "/organizations/invite",
        data={"email": "x@x.com", "role": "member"},
    )
    assert response.status_code == 403


@patch("knowledge.tasks.send_workspace_invitation_email")
@patch("knowledge.routes.web.organizations.get_settings")
async def test_create_invitation_invalid_role(mock_settings, mock_email, web_client, mock_db):
    """Invalid role defaults to MEMBER."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        "/organizations/invite",
        data={"email": "x@x.com", "role": "invalid_role"},
        follow_redirects=False,
    )
    assert response.status_code == 302


@patch("knowledge.tasks.send_workspace_invitation_email")
@patch("knowledge.routes.web.organizations.get_settings")
async def test_create_invitation_owner_role_by_non_owner(
    mock_settings, mock_email, web_client_admin_not_owner, mock_db
):
    """Admin (non-owner) inviting as owner gets downgraded to admin."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client_admin_not_owner.post(
        "/organizations/invite",
        data={"email": "x@x.com", "role": "owner"},
        follow_redirects=False,
    )
    assert response.status_code == 302


# ===========================================================================
# resend_invitation
# ===========================================================================


@patch("knowledge.tasks.send_workspace_invitation_email")
@patch("knowledge.routes.web.organizations.get_settings")
async def test_resend_invitation(mock_settings, mock_email, web_client, mock_db):
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    inv = _make_invitation()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=inv))

    inv_id = uuid4()
    response = await web_client.post(
        f"/organizations/invitations/{inv_id}/resend",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/organizations/members"


async def test_resend_invitation_not_found(web_client, mock_db):
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        f"/organizations/invitations/{uuid4()}/resend",
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_resend_invitation_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        f"/organizations/invitations/{uuid4()}/resend",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


# ===========================================================================
# revoke_invitation
# ===========================================================================


async def test_revoke_invitation(web_client, mock_db):
    inv = _make_invitation()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=inv))

    response = await web_client.post(
        f"/organizations/invitations/{inv.id}/revoke",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert inv.status == InvitationStatus.REVOKED


async def test_revoke_invitation_not_found(web_client, mock_db):
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        f"/organizations/invitations/{uuid4()}/revoke",
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_revoke_invitation_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        f"/organizations/invitations/{uuid4()}/revoke",
        follow_redirects=False,
    )
    assert response.status_code == 302


# ===========================================================================
# remove_member
# ===========================================================================


async def test_remove_member_success(web_client, mock_db):
    other_user_id = uuid4()
    member = _make_mock_member(user_id=other_user_id, role=OrganizationMemberRole.MEMBER)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client.post(
        f"/organizations/members/{member.id}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 302
    mock_db.delete.assert_called_once_with(member)


async def test_remove_member_self(web_client, mock_db):
    """Cannot remove yourself."""
    member = _make_mock_member(user_id=TEST_USER_ID)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client.post(
        f"/organizations/members/{member.id}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 302
    mock_db.delete.assert_not_called()


async def test_remove_owner_by_non_owner(web_client_admin_not_owner, mock_db):
    """Admin cannot remove owner."""
    member = _make_mock_member(
        user_id=uuid4(),
        role=OrganizationMemberRole.OWNER,
    )
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client_admin_not_owner.post(
        f"/organizations/members/{member.id}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 302
    mock_db.delete.assert_not_called()


async def test_remove_member_not_found(web_client, mock_db):
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        f"/organizations/members/{uuid4()}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_remove_member_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        f"/organizations/members/{uuid4()}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 302


# ===========================================================================
# update_member_role
# ===========================================================================


async def test_update_member_role_success(web_client, mock_db):
    other_user_id = uuid4()
    member = _make_mock_member(user_id=other_user_id, role=OrganizationMemberRole.MEMBER)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client.post(
        f"/organizations/members/{member.id}/role",
        data={"role": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert member.role == OrganizationMemberRole.ADMIN


async def test_update_member_role_self(web_client, mock_db):
    """Cannot change own role."""
    member = _make_mock_member(user_id=TEST_USER_ID)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client.post(
        f"/organizations/members/{member.id}/role",
        data={"role": "member"},
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_update_member_role_invalid(web_client, mock_db):
    """Invalid role value is ignored."""
    member = _make_mock_member(user_id=uuid4(), role=OrganizationMemberRole.MEMBER)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client.post(
        f"/organizations/members/{member.id}/role",
        data={"role": "superadmin"},
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_update_member_role_owner_by_non_owner(web_client_admin_not_owner, mock_db):
    """Non-owner promoting to owner gets capped to admin."""
    member = _make_mock_member(user_id=uuid4(), role=OrganizationMemberRole.MEMBER)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=member))

    response = await web_client_admin_not_owner.post(
        f"/organizations/members/{member.id}/role",
        data={"role": "owner"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert member.role == OrganizationMemberRole.ADMIN


async def test_update_member_role_not_found(web_client, mock_db):
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        f"/organizations/members/{uuid4()}/role",
        data={"role": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 302


# ===========================================================================
# view_invitation (public)
# ===========================================================================


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_view_invitation_success(mock_cookie, mock_templates, web_client, mock_db):
    """View valid invitation when not logged in."""
    inv = _make_invitation()
    org = _make_mock_tenant()
    mock_cookie.return_value = None

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=inv),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/invites/inv-token-123")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/invite_view.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_view_invitation_not_found(mock_templates, web_client, mock_db):
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/invites/bad")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/invite_error.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_view_invitation_not_pending(mock_templates, web_client, mock_db):
    inv = _make_invitation(status=InvitationStatus.ACCEPTED)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=inv))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/invites/tok")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/invite_error.html"


@patch("knowledge.routes.web.organizations.templates")
async def test_view_invitation_expired(mock_templates, web_client, mock_db):
    inv = _make_invitation(expires_at=datetime.now(UTC) - timedelta(days=1))
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=inv))
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/invites/tok")
    assert response.status_code == 200
    assert inv.status == InvitationStatus.EXPIRED


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_view_invitation_logged_in(mock_cookie, mock_templates, web_client, mock_db):
    """View invitation when logged in shows user."""
    inv = _make_invitation()
    org = _make_mock_tenant()
    mock_cookie.return_value = "jwt_token"

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=inv),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    with patch("knowledge.auth.jwt.get_jwt_validator") as mock_jwt:
        validator = MagicMock()
        validator.validate_token_with_introspection = AsyncMock(
            return_value={
                "sub": str(TEST_USER_ID),
                "email": "test@example.com",
            }
        )
        mock_jwt.return_value = validator

        response = await web_client.get("/organizations/invites/inv-token-123")
        assert response.status_code == 200
        ctx = mock_templates.TemplateResponse.call_args[0][2]
        assert ctx["user"] is not None


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_view_invitation_logged_in_invalid_token(
    mock_cookie, mock_templates, web_client, mock_db
):
    """View invitation when logged in but token is invalid -> user=None."""
    inv = _make_invitation()
    org = _make_mock_tenant()
    mock_cookie.return_value = "bad_jwt"

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=inv),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    with patch("knowledge.auth.jwt.get_jwt_validator") as mock_jwt:
        validator = MagicMock()
        validator.validate_token_with_introspection = AsyncMock(side_effect=Exception("bad token"))
        mock_jwt.return_value = validator

        response = await web_client.get("/organizations/invites/inv-token-123")
        assert response.status_code == 200
        ctx = mock_templates.TemplateResponse.call_args[0][2]
        assert ctx["user"] is None


# ===========================================================================
# accept_invitation
# ===========================================================================


@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_accept_invitation_not_logged_in(mock_cookie, web_client, mock_db):
    mock_cookie.return_value = None

    response = await web_client.post(
        "/organizations/invites/tok/accept",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_accept_invitation_invalid_token(mock_cookie, web_client, mock_db):
    mock_cookie.return_value = "bad_jwt"

    with patch("knowledge.auth.jwt.get_jwt_validator") as mock_jwt:
        validator = MagicMock()
        validator.validate_token_with_introspection = AsyncMock(side_effect=Exception("bad"))
        mock_jwt.return_value = validator

        response = await web_client.post(
            "/organizations/invites/tok/accept",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/auth/login" in response.headers["location"]


@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_accept_invitation_success(mock_cookie, web_client, mock_db):
    mock_cookie.return_value = "jwt"
    inv = _make_invitation()

    with patch("knowledge.auth.jwt.get_jwt_validator") as mock_jwt:
        validator = MagicMock()
        validator.validate_token_with_introspection = AsyncMock(
            return_value={
                "sub": str(TEST_USER_ID),
                "email": "test@example.com",
            }
        )
        mock_jwt.return_value = validator

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_result(scalar_one_or_none=inv),  # get invitation
                _make_result(scalar_one_or_none=None),  # not already member
            ]
        )

        response = await web_client.post(
            "/organizations/invites/tok/accept",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"
        assert inv.status == InvitationStatus.ACCEPTED
        mock_db.add.assert_called_once()  # new member added


@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_accept_invitation_already_member(mock_cookie, web_client, mock_db):
    mock_cookie.return_value = "jwt"
    inv = _make_invitation()
    existing_member = _make_mock_member()

    with patch("knowledge.auth.jwt.get_jwt_validator") as mock_jwt:
        validator = MagicMock()
        validator.validate_token_with_introspection = AsyncMock(
            return_value={
                "sub": str(TEST_USER_ID),
                "email": "test@example.com",
            }
        )
        mock_jwt.return_value = validator

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_result(scalar_one_or_none=inv),
                _make_result(scalar_one_or_none=existing_member),
            ]
        )

        response = await web_client.post(
            "/organizations/invites/tok/accept",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert inv.status == InvitationStatus.ACCEPTED
        mock_db.add.assert_not_called()


@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_accept_invitation_not_found(mock_cookie, web_client, mock_db):
    mock_cookie.return_value = "jwt"

    with patch("knowledge.auth.jwt.get_jwt_validator") as mock_jwt:
        validator = MagicMock()
        validator.validate_token_with_introspection = AsyncMock(
            return_value={
                "sub": str(TEST_USER_ID),
            }
        )
        mock_jwt.return_value = validator

        mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

        response = await web_client.post(
            "/organizations/invites/tok/accept",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/organizations/invites/tok" in response.headers["location"]


@patch("knowledge.routes.web.organizations.get_token_from_cookie", new_callable=AsyncMock)
async def test_accept_invitation_expired(mock_cookie, web_client, mock_db):
    mock_cookie.return_value = "jwt"
    inv = _make_invitation(expires_at=datetime.now(UTC) - timedelta(days=1))

    with patch("knowledge.auth.jwt.get_jwt_validator") as mock_jwt:
        validator = MagicMock()
        validator.validate_token_with_introspection = AsyncMock(
            return_value={
                "sub": str(TEST_USER_ID),
            }
        )
        mock_jwt.return_value = validator

        mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=inv))

        response = await web_client.post(
            "/organizations/invites/tok/accept",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert inv.status == InvitationStatus.EXPIRED


# ===========================================================================
# custom_domain_page
# ===========================================================================


@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.templates")
async def test_custom_domain_page(mock_templates, mock_settings, mock_db):
    tenant = _make_mock_tenant(can_use_custom_domain=True, plan=PlanType.ENTERPRISE)
    auth = _build_auth(tenant=tenant)

    settings = MagicMock()
    settings.custom_domain_cname_target = "cname.example.com"
    mock_settings.return_value = settings

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    async with AsyncClient(transport=ASGITransport(app=internal_app), base_url="http://test") as ac:
        response = await ac.get("/organizations/domain")

    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/domain.html"
    # the page belongs to the settings: that sidebar item is the active one
    assert mock_templates.TemplateResponse.call_args[0][2]["active_section"] == (
        "organization_settings"
    )
    internal_app.dependency_overrides.clear()


async def test_custom_domain_page_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.get("/organizations/domain", follow_redirects=False)
    assert response.status_code == 302


@patch("knowledge.routes.web.organizations.templates")
async def test_custom_domain_page_non_admin(mock_templates, web_client_non_admin, mock_db):
    mock_templates.TemplateResponse.return_value = _html_response(403)
    response = await web_client_non_admin.get("/organizations/domain")
    assert response.status_code == 403


async def test_custom_domain_page_not_enterprise(web_client, mock_db):
    """Non-enterprise redirect to settings."""
    response = await web_client.get("/organizations/domain", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/organizations/settings"


# ===========================================================================
# update_custom_domain (POST)
# ===========================================================================


def _service_client(**methods):
    """A custom-domain client whose calls succeed unless a test says otherwise."""
    client = MagicMock()
    client.register = AsyncMock(
        return_value=RegisteredDomain(
            id="svc-1",
            domain="custom.example.com",
            status="pending",
            cname_target="apps.example.test",
        )
    )
    client.verify = AsyncMock(return_value="dns_verifying")
    client.delete = AsyncMock(return_value=True)
    for name, value in methods.items():
        setattr(client, name, value)
    return client


async def _post_domain(tenant, mock_db, domain="custom.example.com", client=None, db_result=None):
    auth = _build_auth(tenant=tenant)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth
    mock_db.execute = AsyncMock(return_value=db_result or _make_result(scalar_one_or_none=None))
    settings = MagicMock(custom_domain_cname_target="cname.example.com")
    try:
        with (
            patch("knowledge.routes.web.organizations.get_settings", return_value=settings),
            patch(
                "knowledge.routes.web.organizations.get_custom_domain_client",
                return_value=client or _service_client(),
            ),
            patch("knowledge.routes.web.organizations.templates") as templates,
        ):
            templates.TemplateResponse.return_value = _html_response()
            async with AsyncClient(
                transport=ASGITransport(app=internal_app), base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/organizations/domain", data={"domain": domain}, follow_redirects=False
                )
            context = (
                templates.TemplateResponse.call_args[0][2]
                if templates.TemplateResponse.called
                else None
            )
    finally:
        internal_app.dependency_overrides.clear()
    return response, context


async def test_update_custom_domain_success(mock_db):
    tenant = _make_mock_tenant(can_use_custom_domain=True)
    client = _service_client()

    response, _ = await _post_domain(tenant, mock_db, client=client)

    assert response.status_code == 302
    assert response.headers["location"] == "/organizations/domain"
    client.register.assert_awaited_once_with("custom.example.com", str(tenant.id))
    client.delete.assert_not_called()
    assert tenant.custom_domain == "custom.example.com"
    assert tenant.custom_domain_service_id == "svc-1"
    assert tenant.custom_domain_cname_target == "apps.example.test"
    assert tenant.custom_domain_status == CustomDomainStatus.PENDING
    mock_db.commit.assert_awaited()


async def test_update_custom_domain_replaces_the_previous_domain(mock_db):
    tenant = _make_mock_tenant(
        can_use_custom_domain=True,
        custom_domain="old.example.com",
        custom_domain_service_id="old-id",
    )
    client = _service_client()

    await _post_domain(tenant, mock_db, client=client)

    client.delete.assert_awaited_once_with("old-id")
    assert tenant.custom_domain_service_id == "svc-1"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (CustomDomainError("taken", status_code=409), "already registered"),
        (CustomDomainError("Domain limit reached (5)", status_code=403), "Domain limit reached"),
        (CustomDomainError("down", retryable=True), "not available right now"),
    ],
)
async def test_update_custom_domain_refused_by_the_service(mock_db, error, message):
    tenant = _make_mock_tenant(can_use_custom_domain=True)
    client = _service_client(register=AsyncMock(side_effect=error))

    response, context = await _post_domain(tenant, mock_db, client=client)

    assert response.status_code == 200
    assert message in context["error"]
    assert tenant.custom_domain is None
    mock_db.commit.assert_not_called()


@patch("knowledge.routes.web.organizations.domain_service")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.templates")
async def test_update_custom_domain_invalid(
    mock_templates, mock_settings, mock_domain_svc, mock_db
):
    tenant = _make_mock_tenant(can_use_custom_domain=True)
    auth = _build_auth(tenant=tenant)

    settings = MagicMock()
    settings.custom_domain_cname_target = "cname.example.com"
    mock_settings.return_value = settings
    mock_domain_svc.validate_domain.return_value = (False, "Invalid domain")

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
    mock_templates.TemplateResponse.return_value = _html_response()

    async with AsyncClient(transport=ASGITransport(app=internal_app), base_url="http://test") as ac:
        response = await ac.post("/organizations/domain", data={"domain": "bad"})

    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["error"] == "Invalid domain"
    internal_app.dependency_overrides.clear()


@patch("knowledge.routes.web.organizations.domain_service")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.templates")
async def test_update_custom_domain_already_used(
    mock_templates, mock_settings, mock_domain_svc, mock_db
):
    tenant = _make_mock_tenant(can_use_custom_domain=True)
    auth = _build_auth(tenant=tenant)

    settings = MagicMock()
    settings.custom_domain_cname_target = "cname.example.com"
    mock_settings.return_value = settings
    mock_domain_svc.validate_domain.return_value = (True, "")

    existing_org = _make_mock_tenant(id=uuid4())

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=existing_org),
            _make_result(scalars_all=[]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    async with AsyncClient(transport=ASGITransport(app=internal_app), base_url="http://test") as ac:
        response = await ac.post("/organizations/domain", data={"domain": "used.com"})

    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "already in use" in ctx["error"]
    internal_app.dependency_overrides.clear()


async def test_update_custom_domain_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/domain", data={"domain": "x.com"}, follow_redirects=False
    )
    assert response.status_code == 302


async def test_update_custom_domain_not_enterprise(web_client, mock_db):
    response = await web_client.post(
        "/organizations/domain", data={"domain": "x.com"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/organizations/settings"


# ===========================================================================
# retry_domain_verification
# ===========================================================================


async def _post_action(path, tenant, mock_db, client):
    auth = _build_auth(tenant=tenant)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth
    try:
        with (
            patch(
                "knowledge.routes.web.organizations.get_custom_domain_client", return_value=client
            ),
            patch("knowledge.routes.web.organizations.templates") as templates,
            patch(
                "knowledge.routes.web.organizations.get_settings",
                return_value=MagicMock(custom_domain_cname_target=""),
            ),
        ):
            templates.TemplateResponse.return_value = _html_response()
            async with AsyncClient(
                transport=ASGITransport(app=internal_app), base_url="http://test"
            ) as ac:
                response = await ac.post(path, follow_redirects=False)
            context = (
                templates.TemplateResponse.call_args[0][2]
                if templates.TemplateResponse.called
                else None
            )
    finally:
        internal_app.dependency_overrides.clear()
    return response, context


async def test_retry_domain_verification(mock_db):
    tenant = _make_mock_tenant(custom_domain="test.example.com", custom_domain_service_id="svc-9")
    client = _service_client()

    response, _ = await _post_action("/organizations/domain/verify", tenant, mock_db, client)

    assert response.status_code == 302
    client.verify.assert_awaited_once_with("svc-9")
    client.register.assert_not_called()
    assert tenant.custom_domain_status == CustomDomainStatus.DNS_VERIFYING
    mock_db.commit.assert_awaited()


async def test_retry_registers_a_domain_the_service_does_not_know(mock_db):
    tenant = _make_mock_tenant(custom_domain="test.example.com")
    client = _service_client()

    response, _ = await _post_action("/organizations/domain/verify", tenant, mock_db, client)

    assert response.status_code == 302
    client.register.assert_awaited_once_with("test.example.com", str(tenant.id))
    client.verify.assert_not_called()
    assert tenant.custom_domain_service_id == "svc-1"
    assert tenant.custom_domain_status == CustomDomainStatus.PENDING


async def test_retry_domain_verification_service_error(mock_db):
    tenant = _make_mock_tenant(custom_domain="test.example.com", custom_domain_service_id="svc-9")
    client = _service_client(
        verify=AsyncMock(side_effect=CustomDomainError("Cannot verify", status_code=400))
    )

    response, context = await _post_action("/organizations/domain/verify", tenant, mock_db, client)

    assert response.status_code == 200
    assert context["error"] == "Cannot verify"


async def test_retry_domain_verification_no_domain(mock_db):
    tenant = _make_mock_tenant(custom_domain=None)
    client = _service_client()

    response, _ = await _post_action("/organizations/domain/verify", tenant, mock_db, client)

    assert response.status_code == 302
    client.verify.assert_not_called()
    client.register.assert_not_called()


async def test_retry_domain_verification_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/domain/verify", follow_redirects=False
    )
    assert response.status_code == 302


# ===========================================================================
# domain_status (JSON)
# ===========================================================================


async def test_domain_status_success(mock_db):
    tenant = _make_mock_tenant(
        custom_domain="test.example.com",
        custom_domain_status=CustomDomainStatus.ACTIVE,
        custom_domain_error=None,
    )
    auth = _build_auth(tenant=tenant)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth

    async with AsyncClient(transport=ASGITransport(app=internal_app), base_url="http://test") as ac:
        response = await ac.get("/organizations/domain/status")

    data = response.json()
    assert data["has_domain"] is True
    assert data["status"] == "active"
    internal_app.dependency_overrides.clear()


async def test_domain_status_no_domain(web_client, mock_db):
    response = await web_client.get("/organizations/domain/status")
    data = response.json()
    assert data["has_domain"] is False


async def test_domain_status_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.get("/organizations/domain/status")
    data = response.json()
    assert data["error"] == "No organization selected"


# ===========================================================================
# remove_custom_domain
# ===========================================================================


async def test_remove_custom_domain_success(mock_db):
    tenant = _make_mock_tenant(
        custom_domain="old.example.com",
        custom_domain_service_id="svc-9",
        custom_domain_status=CustomDomainStatus.ACTIVE,
    )
    client = _service_client()

    response, _ = await _post_action("/organizations/domain/remove", tenant, mock_db, client)

    assert response.status_code == 302
    assert response.headers["location"] == "/organizations/domain"
    client.delete.assert_awaited_once_with("svc-9")
    assert tenant.custom_domain is None
    assert tenant.custom_domain_service_id is None
    assert tenant.custom_domain_status is None
    mock_db.commit.assert_awaited()


async def test_remove_custom_domain_without_service_id_only_forgets_it(mock_db):
    tenant = _make_mock_tenant(custom_domain="old.example.com")
    client = _service_client()

    response, _ = await _post_action("/organizations/domain/remove", tenant, mock_db, client)

    assert response.status_code == 302
    client.delete.assert_not_called()
    assert tenant.custom_domain is None


async def test_remove_custom_domain_kept_when_the_service_fails(mock_db):
    tenant = _make_mock_tenant(custom_domain="old.example.com", custom_domain_service_id="svc-9")
    client = _service_client(
        delete=AsyncMock(side_effect=CustomDomainError("down", retryable=True))
    )

    response, context = await _post_action("/organizations/domain/remove", tenant, mock_db, client)

    assert response.status_code == 200
    assert "not available right now" in context["error"]
    assert tenant.custom_domain == "old.example.com"
    mock_db.commit.assert_not_called()


async def test_remove_custom_domain_no_existing(mock_db):
    tenant = _make_mock_tenant(custom_domain=None)
    client = _service_client()

    response, _ = await _post_action("/organizations/domain/remove", tenant, mock_db, client)

    assert response.status_code == 302
    client.delete.assert_not_called()


async def test_remove_custom_domain_no_tenant(web_client_no_tenant):
    response = await web_client_no_tenant.post(
        "/organizations/domain/remove", follow_redirects=False
    )
    assert response.status_code == 302


# ===========================================================================
# Fixture: web_client_redirect (auth returns RedirectResponse)
# ===========================================================================


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


# ===========================================================================
# Auth redirect tests (isinstance(auth_result, RedirectResponse) branches)
# ===========================================================================


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


async def test_delete_organization_auth_redirect(web_client_redirect):
    """Line 462: delete_organization returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/delete",
        data={"confirmation_name": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_confirm_deletion_page_auth_redirect(web_client_redirect):
    """Line 560: confirm_deletion_page returns auth redirect."""
    response = await web_client_redirect.get(
        "/organizations/delete/confirm/some-token",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_execute_deletion_auth_redirect(web_client_redirect):
    """Line 649: execute_deletion returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/delete/confirm/some-token",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_cancel_scheduled_deletion_auth_redirect(web_client_redirect):
    """Line 823: cancel_scheduled_deletion returns auth redirect."""
    response = await web_client_redirect.get(
        "/organizations/delete/cancel/some-cancel-token",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_organization_members_auth_redirect(web_client_redirect):
    """Line 935: organization_members returns auth redirect."""
    response = await web_client_redirect.get("/organizations/members", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_invite_form_auth_redirect(web_client_redirect):
    """Line 989: invite_form returns auth redirect."""
    response = await web_client_redirect.get("/organizations/invite", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_create_invitation_auth_redirect(web_client_redirect):
    """Line 1023: create_invitation returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/invite",
        data={"email": "x@x.com", "role": "member"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_resend_invitation_auth_redirect(web_client_redirect):
    """Line 1113: resend_invitation returns auth redirect."""
    response = await web_client_redirect.post(
        f"/organizations/invitations/{uuid4()}/resend",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_revoke_invitation_auth_redirect(web_client_redirect):
    """Line 1160: revoke_invitation returns auth redirect."""
    response = await web_client_redirect.post(
        f"/organizations/invitations/{uuid4()}/revoke",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_remove_member_auth_redirect(web_client_redirect):
    """Line 1192: remove_member returns auth redirect."""
    response = await web_client_redirect.post(
        f"/organizations/members/{uuid4()}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_update_member_role_auth_redirect(web_client_redirect):
    """Lines 1233, 1236: update_member_role returns auth redirect."""
    response = await web_client_redirect.post(
        f"/organizations/members/{uuid4()}/role",
        data={"role": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_custom_domain_page_auth_redirect(web_client_redirect):
    """Line 1444: custom_domain_page returns auth redirect."""
    response = await web_client_redirect.get("/organizations/domain", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_update_custom_domain_auth_redirect(web_client_redirect):
    """Line 1487: update_custom_domain returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/domain",
        data={"domain": "example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_retry_domain_verification_auth_redirect(web_client_redirect):
    """Line 1566: retry_domain_verification returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/domain/verify", follow_redirects=False
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_domain_status_auth_redirect(web_client_redirect):
    """Line 1587: domain_status returns error dict when auth is RedirectResponse."""
    response = await web_client_redirect.get("/organizations/domain/status", follow_redirects=False)
    # This is a JSON endpoint that returns {"error": "Not authenticated"}
    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "Not authenticated"


async def test_remove_custom_domain_auth_redirect(web_client_redirect):
    """Line 1615: remove_custom_domain returns auth redirect."""
    response = await web_client_redirect.post(
        "/organizations/domain/remove", follow_redirects=False
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


# ===========================================================================
# Branch partial tests
# ===========================================================================


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


@patch("knowledge.routes.web.organizations.templates")
async def test_update_custom_domain_non_admin(mock_templates, web_client_non_admin, mock_db):
    """Line 1493: update_custom_domain returns 403 for non-admin."""
    mock_templates.TemplateResponse.return_value = _html_response(403)

    response = await web_client_non_admin.post(
        "/organizations/domain",
        data={"domain": "example.com"},
    )
    assert response.status_code == 403


@patch("knowledge.routes.web.organizations.templates")
async def test_confirm_deletion_page_expired_not_pending(mock_templates, web_client, mock_db):
    """Branch 581->584: deletion_request.is_expired=True but status is NOT PENDING.

    The code should skip calling mark_expired() and go directly to rendering error.
    """
    dr = _make_deletion_request(
        status=DeletionRequestStatus.CONFIRMED,
        is_expired=True,
    )

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/confirm/tok")
    assert response.status_code == 200
    assert mock_templates.TemplateResponse.call_args[0][1] == "tenants/deletion_error.html"
    # mark_expired should NOT be called because status is not PENDING
    dr.mark_expired.assert_not_called()


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_cancel_scheduled_deletion_billing_not_configured(
    mock_billing, mock_templates, web_client, mock_db
):
    """Branch 889->907: subscription_cancelled=True but billing_client.is_configured=False.

    The code should skip reactivation and proceed to cancel the deletion request.
    """
    dr = _make_deletion_request(
        status=DeletionRequestStatus.SCHEDULED,
        subscription_cancelled=True,
    )
    org = _make_mock_tenant()

    billing = MagicMock()
    billing.is_configured = False
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/tok")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["subscription_reactivated"] is False
    dr.cancel.assert_called_once()
    # billing.get_tenant_subscription should NOT be called
    billing.get_tenant_subscription.assert_not_called()


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_cancel_scheduled_deletion_sub_not_cancel_at_period_end(
    mock_billing, mock_templates, web_client, mock_db
):
    """Branch 892->907: subscription exists but cancel_at_period_end is False.

    The code should skip reactivation.
    """
    dr = _make_deletion_request(
        status=DeletionRequestStatus.SCHEDULED,
        subscription_cancelled=True,
    )
    org = _make_mock_tenant()
    sub = MagicMock()
    sub.id = "sub_123"
    sub.cancel_at_period_end = False

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=sub)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/tok")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["subscription_reactivated"] is False
    dr.cancel.assert_called_once()
    # reactivate_subscription should NOT be called
    billing.reactivate_subscription.assert_not_called()


@patch("knowledge.routes.web.organizations.templates")
@patch("knowledge.routes.web.organizations.get_billing_client")
async def test_cancel_scheduled_deletion_no_subscription(
    mock_billing, mock_templates, web_client, mock_db
):
    """Branch 892->907: subscription is None.

    The code should skip reactivation.
    """
    dr = _make_deletion_request(
        status=DeletionRequestStatus.SCHEDULED,
        subscription_cancelled=True,
    )
    org = _make_mock_tenant()

    billing = MagicMock()
    billing.is_configured = True
    billing.get_tenant_subscription = AsyncMock(return_value=None)
    mock_billing.return_value = billing

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalar_one_or_none=dr),
            _make_result(scalar_one_or_none=org),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/organizations/delete/cancel/tok")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["subscription_reactivated"] is False
    dr.cancel.assert_called_once()
    billing.reactivate_subscription.assert_not_called()


# ===========================================================================
# Additional tests for remaining uncovered lines
# ===========================================================================


@patch("knowledge.routes.web.organizations.get_settings")
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


@patch("knowledge.routes.web.organizations.send_workspace_deletion_email")
@patch("knowledge.routes.web.organizations.get_settings")
@patch("knowledge.routes.web.organizations.templates")
async def test_delete_org_cancels_existing_pending_requests(
    mock_templates, mock_settings, mock_email, web_client, mock_db
):
    """Line 506: existing pending deletion requests are cancelled before creating new one."""
    settings = MagicMock()
    settings.app_base_url = "http://test"
    mock_settings.return_value = settings

    existing_req1 = _make_deletion_request()
    existing_req2 = _make_deletion_request()

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[existing_req1, existing_req2]),  # existing pending requests
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    with (
        patch.object(WorkspaceDeletionRequest, "generate_token", return_value="tok-new"),
        patch.object(
            WorkspaceDeletionRequest,
            "default_expiry",
            return_value=datetime.now(UTC) + timedelta(hours=24),
        ),
    ):
        response = await web_client.post(
            "/organizations/delete",
            data={"confirmation_name": "Test Org"},
        )
    assert response.status_code == 200
    existing_req1.cancel.assert_called_once()
    existing_req2.cancel.assert_called_once()


async def test_update_member_role_no_tenant(web_client_no_tenant):
    """Line 1236: update_member_role redirects to dashboard when no tenant."""
    response = await web_client_no_tenant.post(
        f"/organizations/members/{uuid4()}/role",
        data={"role": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
