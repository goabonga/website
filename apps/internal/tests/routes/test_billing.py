# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.billing route handlers."""

import re
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import RedirectResponse
from internal.auth.models import User
from internal.config import settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**kwargs):
    defaults = {
        "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "email": "test@example.com",
        "name": "Test User",
        "scopes": ["*"],
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    return req


# ---------------------------------------------------------------------------
# billing_dashboard
# ---------------------------------------------------------------------------


class TestBillingDashboard:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.settings")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_settings, mock_client):
        from internal.routes.billing import billing_dashboard

        mock_settings.oauth2_client_id = "cid"
        mock_client.list_saas_apps = AsyncMock(return_value=[{"id": "a1"}])
        user = _make_user()
        request = _make_request(query_params={"success": "ok"})

        await billing_dashboard(request, auth_result=user)

        mock_client.list_saas_apps.assert_awaited_once()
        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["saas_apps"] == [{"id": "a1"}]
        assert ctx["success"] == "ok"

    async def test_redirect_auth(self):
        from internal.routes.billing import billing_dashboard

        redirect = RedirectResponse(url="/login")
        result = await billing_dashboard(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# saas_app_new
# ---------------------------------------------------------------------------


class TestSaasAppNew:
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates):
        from internal.routes.billing import saas_app_new

        user = _make_user()
        request = _make_request(query_params={"error": "oops"})

        await saas_app_new(request, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["saas_app"] is None
        assert ctx["is_edit"] is False
        assert ctx["error"] == "oops"

    async def test_redirect_auth(self):
        from internal.routes.billing import saas_app_new

        redirect = RedirectResponse(url="/login")
        result = await saas_app_new(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# saas_app_create
# ---------------------------------------------------------------------------


class TestSaasAppCreate:
    @patch("internal.routes.billing.billing_client")
    async def test_success(self, mock_client):
        from internal.routes.billing import saas_app_create

        mock_app = MagicMock(id="s1", name="App1")
        mock_client.create_saas_app = AsyncMock(return_value=mock_app)
        user = _make_user()
        request = _make_request()

        result = await saas_app_create(
            request,
            name="App1",
            slug="app1",
            description="desc",
            webhook_url="http://wh",
            webhook_secret="sec",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "/billing/saas/s1" in result.headers["location"]
        mock_client.create_saas_app.assert_awaited_once()

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import saas_app_create

        mock_client.create_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await saas_app_create(
            request,
            name="App1",
            slug="app1",
            description=None,
            webhook_url=None,
            webhook_secret=None,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import saas_app_create

        redirect = RedirectResponse(url="/login")
        result = await saas_app_create(
            MagicMock(),
            name="x",
            slug="x",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# saas_app_detail
# ---------------------------------------------------------------------------


class TestSaasAppDetail:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import saas_app_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_products = AsyncMock(return_value=[])
        mock_client.list_customers = AsyncMock(return_value=[])
        mock_client.list_subscriptions = AsyncMock(return_value=[])
        mock_client.list_saas_clients = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request(query_params={"success": "ok", "error": None})

        await saas_app_detail(request, saas_id="s1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["saas_app"].id == "s1"

    @patch("internal.routes.billing.billing_client")
    async def test_not_found(self, mock_client):
        from internal.routes.billing import saas_app_detail

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await saas_app_detail(request, saas_id="bad", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import saas_app_detail

        redirect = RedirectResponse(url="/login")
        result = await saas_app_detail(MagicMock(), saas_id="s1", auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# saas_app_edit
# ---------------------------------------------------------------------------


class TestSaasAppEdit:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import saas_app_edit

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        user = _make_user()
        request = _make_request()

        await saas_app_edit(request, saas_id="s1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["is_edit"] is True

    @patch("internal.routes.billing.billing_client")
    async def test_not_found(self, mock_client):
        from internal.routes.billing import saas_app_edit

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await saas_app_edit(request, saas_id="bad", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import saas_app_edit

        redirect = RedirectResponse(url="/login")
        result = await saas_app_edit(MagicMock(), saas_id="s1", auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# saas_app_update
# ---------------------------------------------------------------------------


class TestSaasAppUpdate:
    @patch("internal.routes.billing.billing_client")
    async def test_success(self, mock_client):
        from internal.routes.billing import saas_app_update

        mock_client.update_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        user = _make_user()
        request = _make_request()

        result = await saas_app_update(
            request,
            saas_id="s1",
            name="Updated",
            description="desc",
            webhook_url="http://wh",
            webhook_secret="sec",
            is_active=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import saas_app_update

        mock_client.update_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await saas_app_update(
            request,
            saas_id="s1",
            name="Updated",
            description=None,
            webhook_url=None,
            webhook_secret=None,
            is_active=False,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import saas_app_update

        redirect = RedirectResponse(url="/login")
        result = await saas_app_update(
            MagicMock(),
            saas_id="s1",
            name="x",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# products_list
# ---------------------------------------------------------------------------


class TestProductsList:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import products_list

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_products = AsyncMock(return_value=[{"id": "p1"}])
        user = _make_user()
        request = _make_request()

        await products_list(request, saas_id="s1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["products"] == [{"id": "p1"}]

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import products_list

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await products_list(request, saas_id="bad", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import products_list

        redirect = RedirectResponse(url="/login")
        result = await products_list(MagicMock(), saas_id="s1", auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# product_new
# ---------------------------------------------------------------------------


class TestProductNew:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import product_new

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        user = _make_user()
        request = _make_request()

        await product_new(request, saas_id="s1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["product"] is None
        assert ctx["is_edit"] is False

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import product_new

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await product_new(request, saas_id="bad", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import product_new

        redirect = RedirectResponse(url="/login")
        result = await product_new(MagicMock(), saas_id="s1", auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# product_create
# ---------------------------------------------------------------------------


class TestProductCreate:
    @patch("internal.routes.billing.billing_client")
    async def test_success(self, mock_client):
        from internal.routes.billing import product_create

        mock_product = MagicMock(id="p1", stripe_product_id="sp_1")
        mock_client.create_product = AsyncMock(return_value=mock_product)
        user = _make_user()
        request = _make_request()

        result = await product_create(
            request,
            saas_id="s1",
            name="Pro Plan",
            description="desc",
            slug="pro",
            sort_order=1,
            default_trial_days=14,
            is_recommended=True,
            features_json='["feat1"]',
            limits_json='{"max": 10}',
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import product_create

        mock_client.create_product = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await product_create(
            request,
            saas_id="s1",
            name="Pro Plan",
            description="desc",
            slug="pro",
            sort_order=0,
            default_trial_days=0,
            is_recommended=False,
            features_json="[]",
            limits_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.billing import product_create

        user = _make_user()
        request = _make_request()

        result = await product_create(
            request,
            saas_id="s1",
            name="Pro Plan",
            features_json="{invalid json",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_empty_features_and_limits(self, mock_client):
        from internal.routes.billing import product_create

        mock_product = MagicMock(id="p1", stripe_product_id="sp_1")
        mock_client.create_product = AsyncMock(return_value=mock_product)
        user = _make_user()
        request = _make_request()

        result = await product_create(
            request,
            saas_id="s1",
            name="Plan",
            description="",
            slug="",
            sort_order=0,
            default_trial_days=0,
            is_recommended=False,
            features_json="",
            limits_json="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_zero_trial_days(self, mock_client):
        from internal.routes.billing import product_create

        mock_product = MagicMock(id="p1", stripe_product_id="sp_1")
        mock_client.create_product = AsyncMock(return_value=mock_product)
        user = _make_user()
        request = _make_request()

        await product_create(
            request,
            saas_id="s1",
            name="Plan",
            description="",
            slug="",
            sort_order=0,
            default_trial_days=0,
            is_recommended=False,
            features_json="[]",
            limits_json="{}",
            auth_result=user,
        )

        # Verify that default_trial_days=None is passed in metadata when 0
        call_kwargs = mock_client.create_product.call_args[1]
        assert call_kwargs["metadata"]["default_trial_days"] is None

    async def test_redirect_auth(self):
        from internal.routes.billing import product_create

        redirect = RedirectResponse(url="/login")
        result = await product_create(
            MagicMock(),
            saas_id="s1",
            name="x",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# product_detail
# ---------------------------------------------------------------------------


class TestProductDetail:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import product_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_product = AsyncMock(return_value=MagicMock(id="p1"))
        mock_client.list_prices = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await product_detail(request, saas_id="s1", product_id="p1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["product"].id == "p1"

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import product_detail

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await product_detail(request, saas_id="bad", product_id="p1", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_product_not_found(self, mock_client):
        from internal.routes.billing import product_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_product = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await product_detail(request, saas_id="s1", product_id="bad", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import product_detail

        redirect = RedirectResponse(url="/login")
        result = await product_detail(
            MagicMock(),
            saas_id="s1",
            product_id="p1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# product_edit
# ---------------------------------------------------------------------------


class TestProductEdit:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import product_edit

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_product = AsyncMock(return_value=MagicMock(id="p1"))
        user = _make_user()
        request = _make_request()

        await product_edit(request, saas_id="s1", product_id="p1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["is_edit"] is True

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import product_edit

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await product_edit(request, saas_id="bad", product_id="p1", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_product_not_found(self, mock_client):
        from internal.routes.billing import product_edit

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_product = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await product_edit(request, saas_id="s1", product_id="bad", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import product_edit

        redirect = RedirectResponse(url="/login")
        result = await product_edit(
            MagicMock(),
            saas_id="s1",
            product_id="p1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# product_update
# ---------------------------------------------------------------------------


class TestProductUpdate:
    @patch("internal.routes.billing.billing_client")
    async def test_success(self, mock_client):
        from internal.routes.billing import product_update

        mock_client.update_product = AsyncMock(return_value=MagicMock(id="p1"))
        user = _make_user()
        request = _make_request()

        result = await product_update(
            request,
            saas_id="s1",
            product_id="p1",
            name="Updated",
            description="d",
            slug="up",
            sort_order=2,
            default_trial_days=7,
            is_recommended=False,
            is_active=True,
            features_json='["f1"]',
            limits_json='{"x": 1}',
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import product_update

        mock_client.update_product = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await product_update(
            request,
            saas_id="s1",
            product_id="p1",
            name="Updated",
            description="d",
            slug="up",
            sort_order=0,
            default_trial_days=0,
            is_recommended=False,
            is_active=True,
            features_json="[]",
            limits_json="{}",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_invalid_json(self, mock_client):
        from internal.routes.billing import product_update

        user = _make_user()
        request = _make_request()

        result = await product_update(
            request,
            saas_id="s1",
            product_id="p1",
            name="Updated",
            features_json="{bad",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_empty_features_and_limits(self, mock_client):
        from internal.routes.billing import product_update

        mock_client.update_product = AsyncMock(return_value=MagicMock(id="p1"))
        user = _make_user()
        request = _make_request()

        result = await product_update(
            request,
            saas_id="s1",
            product_id="p1",
            name="Updated",
            description="",
            slug="",
            sort_order=0,
            default_trial_days=0,
            is_recommended=False,
            is_active=True,
            features_json="",
            limits_json="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import product_update

        redirect = RedirectResponse(url="/login")
        result = await product_update(
            MagicMock(),
            saas_id="s1",
            product_id="p1",
            name="x",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# price_new
# ---------------------------------------------------------------------------


class TestPriceNew:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import price_new

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_product = AsyncMock(return_value=MagicMock(id="p1"))
        user = _make_user()
        request = _make_request()

        await price_new(request, saas_id="s1", product_id="p1", auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()

    @patch("internal.routes.billing.billing_client")
    async def test_resource_not_found_saas(self, mock_client):
        from internal.routes.billing import price_new

        mock_client.get_saas_app = AsyncMock(return_value=None)
        mock_client.get_product = AsyncMock(return_value=MagicMock(id="p1"))
        user = _make_user()
        request = _make_request()

        result = await price_new(request, saas_id="bad", product_id="p1", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_resource_not_found_product(self, mock_client):
        from internal.routes.billing import price_new

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_product = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await price_new(request, saas_id="s1", product_id="bad", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import price_new

        redirect = RedirectResponse(url="/login")
        result = await price_new(
            MagicMock(),
            saas_id="s1",
            product_id="p1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# price_create
# ---------------------------------------------------------------------------


class TestPriceCreate:
    @patch("internal.routes.billing.billing_client")
    async def test_success_recurring(self, mock_client):
        from internal.routes.billing import price_create

        mock_price = MagicMock(stripe_price_id="sp_1")
        mock_client.create_price = AsyncMock(return_value=mock_price)
        user = _make_user()
        request = _make_request()

        result = await price_create(
            request,
            saas_id="s1",
            product_id="p1",
            unit_amount=1000,
            currency="eur",
            billing_type="recurring",
            recurring_interval="month",
            usage_type="licensed",
            nickname="Monthly",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]
        # Recurring should pass recurring_interval
        call_kwargs = mock_client.create_price.call_args[1]
        assert call_kwargs["recurring_interval"] == "month"

    @patch("internal.routes.billing.billing_client")
    async def test_success_one_time(self, mock_client):
        from internal.routes.billing import price_create

        mock_price = MagicMock(stripe_price_id="sp_2")
        mock_client.create_price = AsyncMock(return_value=mock_price)
        user = _make_user()
        request = _make_request()

        result = await price_create(
            request,
            saas_id="s1",
            product_id="p1",
            unit_amount=500,
            currency=" USD ",
            billing_type="one_time",
            recurring_interval="month",
            usage_type="licensed",
            nickname=None,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        # One-time should pass None for recurring_interval
        call_kwargs = mock_client.create_price.call_args[1]
        assert call_kwargs["recurring_interval"] is None
        assert call_kwargs["currency"] == "usd"

    @patch("internal.routes.billing.billing_client")
    async def test_blank_fields_are_left_to_the_billing_service(self, mock_client):
        from internal.routes.billing import price_create

        mock_client.create_price = AsyncMock(return_value=MagicMock(stripe_price_id="sp_3"))

        await price_create(
            _make_request(),
            saas_id="s1",
            product_id="p1",
            unit_amount=500,
            currency="",
            billing_type="recurring",
            recurring_interval="",
            usage_type="licensed",
            nickname="",
            auth_result=_make_user(),
        )

        call_kwargs = mock_client.create_price.call_args[1]
        assert call_kwargs["currency"] is None
        assert call_kwargs["recurring_interval"] is None
        assert call_kwargs["nickname"] is None

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import price_create

        mock_client.create_price = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await price_create(
            request,
            saas_id="s1",
            product_id="p1",
            unit_amount=1000,
            currency="",
            billing_type="recurring",
            recurring_interval="",
            usage_type="licensed",
            nickname=None,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import price_create

        redirect = RedirectResponse(url="/login")
        result = await price_create(
            MagicMock(),
            saas_id="s1",
            product_id="p1",
            unit_amount=100,
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# price_toggle
# ---------------------------------------------------------------------------


class TestPriceToggle:
    @patch("internal.routes.billing.billing_client")
    async def test_activate(self, mock_client):
        from internal.routes.billing import price_toggle

        price_obj = MagicMock(id="pr1", is_active=False)
        mock_client.list_prices = AsyncMock(return_value=[price_obj])
        mock_client.update_price = AsyncMock(return_value=MagicMock())
        user = _make_user()
        request = _make_request()

        result = await price_toggle(
            request,
            saas_id="s1",
            product_id="p1",
            price_id="pr1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "activated" in result.headers["location"]
        mock_client.update_price.assert_awaited_once_with(
            saas_id="s1",
            product_id="p1",
            price_id="pr1",
            is_active=True,
        )

    @patch("internal.routes.billing.billing_client")
    async def test_deactivate(self, mock_client):
        from internal.routes.billing import price_toggle

        price_obj = MagicMock(id="pr1", is_active=True)
        mock_client.list_prices = AsyncMock(return_value=[price_obj])
        mock_client.update_price = AsyncMock(return_value=MagicMock())
        user = _make_user()
        request = _make_request()

        result = await price_toggle(
            request,
            saas_id="s1",
            product_id="p1",
            price_id="pr1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "deactivated" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_price_not_found(self, mock_client):
        from internal.routes.billing import price_toggle

        mock_client.list_prices = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        result = await price_toggle(
            request,
            saas_id="s1",
            product_id="p1",
            price_id="nope",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_update_failure(self, mock_client):
        from internal.routes.billing import price_toggle

        price_obj = MagicMock(id="pr1", is_active=True)
        mock_client.list_prices = AsyncMock(return_value=[price_obj])
        mock_client.update_price = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await price_toggle(
            request,
            saas_id="s1",
            product_id="p1",
            price_id="pr1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import price_toggle

        redirect = RedirectResponse(url="/login")
        result = await price_toggle(
            MagicMock(),
            saas_id="s1",
            product_id="p1",
            price_id="pr1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# customers_list
# ---------------------------------------------------------------------------


class TestCustomersList:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import customers_list

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_customers = AsyncMock(return_value=[{"id": "c1"}])
        user = _make_user()
        request = _make_request()

        await customers_list(request, saas_id="s1", page=2, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["page"] == 2
        # The template offers the next page when a full page came back
        assert ctx["per_page"] == settings.billing_page_size

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import customers_list

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await customers_list(request, saas_id="bad", page=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import customers_list

        redirect = RedirectResponse(url="/login")
        result = await customers_list(MagicMock(), saas_id="s1", page=1, auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# customer_detail
# ---------------------------------------------------------------------------


class TestCustomerDetail:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import customer_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_customer = AsyncMock(return_value=MagicMock(id="c1"))
        sub1 = MagicMock(customer_id="c1")
        mock_client.list_customer_subscriptions = AsyncMock(return_value=[sub1])
        user = _make_user()
        request = _make_request()

        await customer_detail(
            request,
            saas_id="s1",
            customer_id="c1",
            auth_result=user,
        )

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["subscriptions"] == [sub1]
        mock_client.list_customer_subscriptions.assert_awaited_once_with("s1", "c1")

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import customer_detail

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await customer_detail(
            request,
            saas_id="bad",
            customer_id="c1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_customer_not_found(self, mock_client):
        from internal.routes.billing import customer_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_customer = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await customer_detail(
            request,
            saas_id="s1",
            customer_id="bad",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import customer_detail

        redirect = RedirectResponse(url="/login")
        result = await customer_detail(
            MagicMock(),
            saas_id="s1",
            customer_id="c1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# customer_portal_redirect
# ---------------------------------------------------------------------------


class TestCustomerPortalRedirect:
    @patch("internal.routes.billing.billing_client")
    async def test_success_returns_to_the_first_allowed_url(self, mock_client):
        from internal.routes.billing import customer_portal_redirect

        portal = MagicMock(url="https://portal.stripe.com/abc")
        mock_client.get_saas_app = AsyncMock(
            return_value=MagicMock(
                checkout_url_allowlist=["https://app.example.test", "https://other.example.test"]
            )
        )
        mock_client.get_customer_portal = AsyncMock(return_value=portal)
        user = _make_user()
        request = _make_request()

        result = await customer_portal_redirect(
            request,
            saas_id="s1",
            customer_id="c1",
            return_url="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "https://portal.stripe.com/abc"
        mock_client.get_customer_portal.assert_awaited_once_with(
            "s1", "c1", "https://app.example.test"
        )

    @patch("internal.routes.billing.billing_client")
    async def test_explicit_return_url_wins(self, mock_client):
        from internal.routes.billing import customer_portal_redirect

        mock_client.get_saas_app = AsyncMock(
            return_value=MagicMock(checkout_url_allowlist=["https://app.example.test"])
        )
        mock_client.get_customer_portal = AsyncMock(
            return_value=MagicMock(url="https://portal.stripe.com/abc")
        )

        await customer_portal_redirect(
            _make_request(),
            saas_id="s1",
            customer_id="c1",
            return_url=" https://app.example.test/billing ",
            auth_result=_make_user(),
        )

        mock_client.get_customer_portal.assert_awaited_once_with(
            "s1", "c1", "https://app.example.test/billing"
        )

    @patch("internal.routes.billing.billing_client")
    async def test_no_return_url_available(self, mock_client):
        from internal.routes.billing import customer_portal_redirect

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(checkout_url_allowlist=None))
        mock_client.get_customer_portal = AsyncMock()

        result = await customer_portal_redirect(
            _make_request(),
            saas_id="s1",
            customer_id="c1",
            return_url="",
            auth_result=_make_user(),
        )

        assert isinstance(result, RedirectResponse)
        assert "error=No+return+URL" in result.headers["location"]
        mock_client.get_customer_portal.assert_not_awaited()

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import customer_portal_redirect

        mock_client.get_saas_app = AsyncMock(
            return_value=MagicMock(checkout_url_allowlist=["https://app.example.test"])
        )
        mock_client.get_customer_portal = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await customer_portal_redirect(
            request,
            saas_id="s1",
            customer_id="c1",
            return_url="",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import customer_portal_redirect

        redirect = RedirectResponse(url="/login")
        result = await customer_portal_redirect(
            MagicMock(),
            saas_id="s1",
            customer_id="c1",
            return_url="",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# subscriptions_list
# ---------------------------------------------------------------------------


class TestSubscriptionsList:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import subscriptions_list

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_subscriptions = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await subscriptions_list(
            request,
            saas_id="s1",
            status="active",
            page=1,
            auth_result=user,
        )

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["status_filter"] == "active"
        assert ctx["per_page"] == settings.billing_page_size

    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success_no_status(self, mock_templates, mock_client):
        from internal.routes.billing import subscriptions_list

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_subscriptions = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await subscriptions_list(
            request,
            saas_id="s1",
            status=None,
            page=1,
            auth_result=user,
        )

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["status_filter"] is None

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import subscriptions_list

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await subscriptions_list(
            request, saas_id="bad", status=None, page=1, auth_result=user
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import subscriptions_list

        redirect = RedirectResponse(url="/login")
        result = await subscriptions_list(
            MagicMock(), saas_id="s1", status=None, page=1, auth_result=redirect
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# subscription_detail
# ---------------------------------------------------------------------------


class TestSubscriptionDetail:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.billing import subscription_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        sub_mock = MagicMock(customer_id="c1")
        mock_client.get_subscription = AsyncMock(return_value=sub_mock)
        mock_client.get_customer = AsyncMock(return_value=MagicMock(id="c1"))
        user = _make_user()
        request = _make_request()

        await subscription_detail(
            request,
            saas_id="s1",
            subscription_id="sub1",
            auth_result=user,
        )

        mock_templates.TemplateResponse.assert_called_once()

    @patch("internal.routes.billing.billing_client")
    async def test_saas_not_found(self, mock_client):
        from internal.routes.billing import subscription_detail

        mock_client.get_saas_app = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await subscription_detail(
            request,
            saas_id="bad",
            subscription_id="sub1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_subscription_not_found(self, mock_client):
        from internal.routes.billing import subscription_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.get_subscription = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await subscription_detail(
            request,
            saas_id="s1",
            subscription_id="bad",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import subscription_detail

        redirect = RedirectResponse(url="/login")
        result = await subscription_detail(
            MagicMock(),
            saas_id="s1",
            subscription_id="sub1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# subscription_cancel
# ---------------------------------------------------------------------------


class TestSubscriptionCancel:
    @patch("internal.routes.billing.billing_client")
    async def test_cancel_at_period_end(self, mock_client):
        from internal.routes.billing import subscription_cancel

        mock_client.cancel_subscription = AsyncMock(return_value=MagicMock())
        user = _make_user()
        request = _make_request()

        result = await subscription_cancel(
            request,
            saas_id="s1",
            subscription_id="sub1",
            cancel_immediately=False,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "scheduled" in result.headers["location"]
        mock_client.cancel_subscription.assert_awaited_once_with(
            saas_id="s1",
            subscription_id="sub1",
            cancel_at_period_end=True,
        )

    @patch("internal.routes.billing.billing_client")
    async def test_cancel_immediately(self, mock_client):
        from internal.routes.billing import subscription_cancel

        mock_client.cancel_subscription = AsyncMock(return_value=MagicMock())
        user = _make_user()
        request = _make_request()

        result = await subscription_cancel(
            request,
            saas_id="s1",
            subscription_id="sub1",
            cancel_immediately=True,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "canceled" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import subscription_cancel

        mock_client.cancel_subscription = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await subscription_cancel(
            request,
            saas_id="s1",
            subscription_id="sub1",
            cancel_immediately=False,
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import subscription_cancel

        redirect = RedirectResponse(url="/login")
        result = await subscription_cancel(
            MagicMock(),
            saas_id="s1",
            subscription_id="sub1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# subscription_sync
# ---------------------------------------------------------------------------


class TestSubscriptionSync:
    @patch("internal.routes.billing.billing_client")
    async def test_success(self, mock_client):
        from internal.routes.billing import subscription_sync

        mock_client.sync_subscription = AsyncMock(return_value=MagicMock())
        user = _make_user()
        request = _make_request()

        result = await subscription_sync(
            request,
            saas_id="s1",
            subscription_id="sub1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import subscription_sync

        mock_client.sync_subscription = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await subscription_sync(
            request,
            saas_id="s1",
            subscription_id="sub1",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import subscription_sync

        redirect = RedirectResponse(url="/login")
        result = await subscription_sync(
            MagicMock(),
            saas_id="s1",
            subscription_id="sub1",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# subscription_reactivate
# ---------------------------------------------------------------------------


class TestSubscriptionReactivate:
    @patch("internal.routes.billing.billing_client")
    async def test_success(self, mock_client):
        from internal.routes.billing import subscription_reactivate

        mock_client.reactivate_subscription = AsyncMock(return_value=MagicMock())

        result = await subscription_reactivate(
            _make_request(), saas_id="s1", subscription_id="sub1", auth_result=_make_user()
        )

        assert isinstance(result, RedirectResponse)
        assert "success=Subscription+reactivated" in result.headers["location"]
        mock_client.reactivate_subscription.assert_awaited_once_with(
            saas_id="s1", subscription_id="sub1"
        )

    @patch("internal.routes.billing.billing_client")
    async def test_failure(self, mock_client):
        from internal.routes.billing import subscription_reactivate

        mock_client.reactivate_subscription = AsyncMock(return_value=None)

        result = await subscription_reactivate(
            _make_request(), saas_id="s1", subscription_id="sub1", auth_result=_make_user()
        )

        assert isinstance(result, RedirectResponse)
        assert "error=Failed+to+reactivate" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.billing import subscription_reactivate

        redirect = RedirectResponse(url="/login")
        result = await subscription_reactivate(
            MagicMock(), saas_id="s1", subscription_id="sub1", auth_result=redirect
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# Behaviour against the partitioned billing service
# ---------------------------------------------------------------------------


class TestAdminView:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_dashboard_lists_inactive_apps(self, mock_templates, mock_client):
        from internal.routes.billing import billing_dashboard

        mock_client.list_saas_apps = AsyncMock(return_value=[])

        await billing_dashboard(_make_request(), auth_result=_make_user())

        mock_client.list_saas_apps.assert_awaited_once_with(include_inactive=True)

    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_products_list_includes_inactive_products(self, mock_templates, mock_client):
        from internal.routes.billing import products_list

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_products = AsyncMock(return_value=[])

        await products_list(_make_request(), saas_id="s1", auth_result=_make_user())

        mock_client.list_products.assert_awaited_once_with("s1", include_inactive=True)

    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_saas_detail_uses_the_configured_recent_limit(self, mock_templates, mock_client):
        from internal.routes.billing import saas_app_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_products = AsyncMock(return_value=[])
        mock_client.list_customers = AsyncMock(return_value=[])
        mock_client.list_subscriptions = AsyncMock(return_value=[])
        mock_client.list_saas_clients = AsyncMock(return_value=[])

        with patch("internal.routes.billing.settings") as s:
            s.billing_recent_limit = 3
            await saas_app_detail(_make_request(), saas_id="s1", auth_result=_make_user())

        mock_client.list_customers.assert_awaited_once_with("s1", limit=3)
        mock_client.list_subscriptions.assert_awaited_once_with("s1", limit=3)

    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_lists_use_the_configured_page_size(self, mock_templates, mock_client):
        from internal.routes.billing import customers_list, subscriptions_list

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_customers = AsyncMock(return_value=[])
        mock_client.list_subscriptions = AsyncMock(return_value=[])

        with patch("internal.routes.billing.settings") as s:
            s.billing_page_size = 5
            await customers_list(_make_request(), saas_id="s1", page=3, auth_result=_make_user())
            await subscriptions_list(
                _make_request(), saas_id="s1", status="active", page=2, auth_result=_make_user()
            )

        mock_client.list_customers.assert_awaited_once_with("s1", limit=5, offset=10)
        mock_client.list_subscriptions.assert_awaited_once_with(
            "s1", status="active", limit=5, offset=5
        )

    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_status_filter_offers_every_billing_status(self, mock_templates, mock_client):
        from internal.routes.billing import subscriptions_list

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_subscriptions = AsyncMock(return_value=[])

        await subscriptions_list(
            _make_request(), saas_id="s1", status=None, page=1, auth_result=_make_user()
        )

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert {"active", "trialing", "past_due", "unpaid", "paused", "canceled"} <= set(
            ctx["statuses"]
        )
        assert {"incomplete", "incomplete_expired"} <= set(ctx["statuses"])


class TestUncheckedCheckboxes:
    """A checkbox that is not ticked is absent from the form: it must read as false."""

    def test_saas_app_update_deactivates_when_the_box_is_absent(self):
        import inspect

        from internal.routes.billing import product_update, saas_app_update

        for handler in (saas_app_update, product_update):
            default = inspect.signature(handler).parameters["is_active"].default
            assert default.default is False


# ---------------------------------------------------------------------------
# Templates (rendered for real)
# ---------------------------------------------------------------------------


def _render(name: str, **context) -> str:
    from internal.routes.billing import templates

    context.setdefault("user", _make_user())
    context.setdefault("active_section", "billing")
    context.setdefault("request", MagicMock())
    return templates.get_template(f"admin/billing/{name}").render(**context)


_APP_NAME = "Acme"


class TestTemplates:
    def test_product_form_has_no_preset_limit_names(self):
        app = MagicMock(id="s1")
        app.name = _APP_NAME
        html = _render("product_form.html", saas_app=app, product=None, is_edit=False, error=None)
        assert "limit-presets" not in html
        assert "max_collections" not in html
        assert "max_storage_bytes" not in html

    def test_product_form_keeps_the_limits_of_the_product(self):
        app = MagicMock(id="s1")
        app.name = _APP_NAME
        product = MagicMock(id="p1", is_active=True)
        product.name = "Pro"
        product.description = None
        product.extra_data = {"limits": {"seats": 5}, "features": []}
        html = _render("product_form.html", saas_app=app, product=product, is_edit=True, error=None)
        assert 'value="seats"' in html
        assert 'value="5"' in html

    def test_active_box_is_only_offered_when_editing(self):
        app = MagicMock(id="s1")
        app.name = _APP_NAME
        product = MagicMock(id="p1", is_active=False)
        product.name = "Pro"
        product.description = None
        product.extra_data = {}
        creating = _render(
            "product_form.html", saas_app=app, product=None, is_edit=False, error=None
        )
        editing = _render(
            "product_form.html", saas_app=app, product=product, is_edit=True, error=None
        )
        assert 'name="is_active"' not in creating
        assert 'name="is_active"' in editing
        # An inactive product shows the box unticked
        assert re.search(r'name="is_active"\s+value="true"\s*>', editing)

    def test_price_form_leaves_currency_and_interval_to_the_service(self):
        app = MagicMock(id="s1")
        app.name = _APP_NAME
        product = MagicMock(id="p1")
        product.name = "Pro"
        html = _render("price_form.html", saas_app=app, product=product, error=None)
        assert 'value="eur"' not in html
        assert 'name="currency"' in html
        assert '<option value="" selected>' in html

    def test_subscription_scheduled_for_cancellation_can_be_reactivated(self):
        app = MagicMock(id="s1")
        app.name = _APP_NAME
        sub = MagicMock(id="sub1", status="active", cancel_at_period_end=True)
        sub.stripe_subscription_id = "stripe_sub"
        sub.created_at = datetime(2024, 1, 1)
        sub.current_period_start = sub.current_period_end = datetime(2024, 2, 1)
        sub.canceled_at = None
        html = _render("subscription_detail.html", saas_app=app, subscription=sub, customer=None)
        assert "/subscriptions/sub1/reactivate" in html
        assert "/subscriptions/sub1/cancel" not in html

    def test_running_subscription_offers_cancellation_not_reactivation(self):
        app = MagicMock(id="s1")
        app.name = _APP_NAME
        sub = MagicMock(id="sub1", status="active", cancel_at_period_end=False)
        sub.stripe_subscription_id = "stripe_sub"
        sub.created_at = datetime(2024, 1, 1)
        sub.current_period_start = sub.current_period_end = datetime(2024, 2, 1)
        sub.canceled_at = None
        html = _render("subscription_detail.html", saas_app=app, subscription=sub, customer=None)
        assert "/subscriptions/sub1/cancel" in html
        assert "/reactivate" not in html


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestBillingSettings:
    def test_defaults_are_neutral(self, monkeypatch):
        from internal.config import Settings

        for name in (
            "BILLING_API_URL",
            "BILLING_SOCKET_PATH",
            "BILLING_READ_SCOPE",
            "BILLING_WRITE_SCOPE",
            "BILLING_ADMIN_SCOPE",
            "BILLING_TIMEOUT",
            "BILLING_PAGE_SIZE",
            "BILLING_RECENT_LIMIT",
        ):
            monkeypatch.delenv(name, raising=False)
        settings = Settings(_env_file=None)

        assert settings.billing_api_url == ""
        assert settings.billing_socket_path == ""
        assert settings.billing_read_scope == "billing:platform:read"
        assert settings.billing_write_scope == "billing:platform:write"
        assert settings.billing_admin_scope == "billing:admin"
        assert settings.billing_timeout == 30.0
        assert settings.billing_page_size == 20
        assert settings.billing_recent_limit == 10

    def test_scopes_follow_the_environment(self, monkeypatch):
        from internal.config import Settings

        monkeypatch.setenv("BILLING_ADMIN_SCOPE", "billing:root")
        monkeypatch.setenv("BILLING_READ_SCOPE", "billing:r")
        settings = Settings(_env_file=None)

        assert settings.billing_admin_scope == "billing:root"
        assert settings.billing_read_scope == "billing:r"


# ---------------------------------------------------------------------------
# OAuth client bindings
# ---------------------------------------------------------------------------


class TestSaasClientBindings:
    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_detail_lists_the_bindings_for_an_administrator(
        self, mock_templates, mock_client
    ):
        from internal.routes.billing import saas_app_detail

        binding = MagicMock(client_id="client-a")
        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_products = AsyncMock(return_value=[])
        mock_client.list_customers = AsyncMock(return_value=[])
        mock_client.list_subscriptions = AsyncMock(return_value=[])
        mock_client.list_saas_clients = AsyncMock(return_value=[binding])

        await saas_app_detail(
            _make_request(), saas_id="s1", auth_result=_make_user(scopes=["billing:admin"])
        )

        mock_client.list_saas_clients.assert_awaited_once_with("s1")
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["bindings"] == [binding]

    @patch("internal.routes.billing.billing_client")
    @patch("internal.routes.billing.templates")
    async def test_detail_does_not_fetch_the_bindings_without_the_admin_scope(
        self, mock_templates, mock_client
    ):
        from internal.routes.billing import saas_app_detail

        mock_client.get_saas_app = AsyncMock(return_value=MagicMock(id="s1"))
        mock_client.list_products = AsyncMock(return_value=[])
        mock_client.list_customers = AsyncMock(return_value=[])
        mock_client.list_subscriptions = AsyncMock(return_value=[])
        mock_client.list_saas_clients = AsyncMock()

        await saas_app_detail(
            _make_request(), saas_id="s1", auth_result=_make_user(scopes=["billing:read"])
        )

        mock_client.list_saas_clients.assert_not_awaited()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["bindings"] == []

    @patch("internal.routes.billing.billing_client")
    async def test_bind_success(self, mock_client):
        from internal.routes.billing import saas_client_bind

        mock_client.bind_client = AsyncMock(return_value=MagicMock())

        result = await saas_client_bind(
            _make_request(), saas_id="s1", client_id=" client-a ", auth_result=_make_user()
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/billing/saas/s1?success=Client+bound"
        mock_client.bind_client.assert_awaited_once_with("s1", "client-a")

    @patch("internal.routes.billing.billing_client")
    async def test_bind_failure(self, mock_client):
        from internal.routes.billing import saas_client_bind

        mock_client.bind_client = AsyncMock(return_value=None)

        result = await saas_client_bind(
            _make_request(), saas_id="s1", client_id="client-a", auth_result=_make_user()
        )

        assert "error=Failed+to+bind+client" in result.headers["location"]

    @patch("internal.routes.billing.billing_client")
    async def test_bind_rejects_a_blank_or_spaced_client_id(self, mock_client):
        from internal.routes.billing import saas_client_bind

        mock_client.bind_client = AsyncMock()

        for client_id in ("", "   ", "two words"):
            result = await saas_client_bind(
                _make_request(), saas_id="s1", client_id=client_id, auth_result=_make_user()
            )
            assert "error=" in result.headers["location"]

        mock_client.bind_client.assert_not_awaited()

    async def test_bind_redirect_auth(self):
        from internal.routes.billing import saas_client_bind

        redirect = RedirectResponse(url="/login")
        result = await saas_client_bind(
            MagicMock(), saas_id="s1", client_id="x", auth_result=redirect
        )
        assert result is redirect

    @patch("internal.routes.billing.billing_client")
    async def test_unbind_success(self, mock_client):
        from internal.routes.billing import saas_client_unbind

        mock_client.unbind_client = AsyncMock(return_value=True)

        result = await saas_client_unbind(
            _make_request(), saas_id="s1", client_id="client-a", auth_result=_make_user()
        )

        assert result.headers["location"] == "/billing/saas/s1?success=Client+unbound"
        mock_client.unbind_client.assert_awaited_once_with("s1", "client-a")

    @patch("internal.routes.billing.billing_client")
    async def test_unbind_failure(self, mock_client):
        from internal.routes.billing import saas_client_unbind

        mock_client.unbind_client = AsyncMock(return_value=False)

        result = await saas_client_unbind(
            _make_request(), saas_id="s1", client_id="client-a", auth_result=_make_user()
        )

        assert "error=Failed+to+unbind+client" in result.headers["location"]

    async def test_unbind_redirect_auth(self):
        from internal.routes.billing import saas_client_unbind

        redirect = RedirectResponse(url="/login")
        result = await saas_client_unbind(
            MagicMock(), saas_id="s1", client_id="x", auth_result=redirect
        )
        assert result is redirect

    async def test_binding_through_the_application_with_the_admin_scope(self, tmp_path):
        from ..sidebar import running_app

        async with running_app(tmp_path) as env:
            billing = env.client("billing.billing_client")
            billing.bind_client.return_value = MagicMock()
            billing.unbind_client.return_value = True

            bound = await env.post(
                "/billing/saas/saas-1/clients", ["billing:*"], {"client_id": "client-a"}
            )
            unbound = await env.post(
                "/billing/saas/saas-1/clients/unbind", ["billing:*"], {"client_id": "client-a"}
            )

        assert bound.status_code == 303
        assert bound.headers["location"] == "/billing/saas/saas-1?success=Client+bound"
        assert unbound.status_code == 303
        assert unbound.headers["location"] == "/billing/saas/saas-1?success=Client+unbound"
        billing.bind_client.assert_awaited_once_with("saas-1", "client-a")

    async def test_binding_through_the_application_needs_the_admin_scope(self, tmp_path):
        from ..sidebar import running_app

        async with running_app(tmp_path) as env:
            billing = env.client("billing.billing_client")
            scopes = ["billing:read", "billing:write", "billing:delete"]

            bound = await env.post(
                "/billing/saas/saas-1/clients", scopes, {"client_id": "client-a"}
            )
            unbound = await env.post(
                "/billing/saas/saas-1/clients/unbind", scopes, {"client_id": "client-a"}
            )

        assert bound.status_code == 403
        assert unbound.status_code == 403
        billing.bind_client.assert_not_awaited()
        billing.unbind_client.assert_not_awaited()

    def test_the_forms_are_reserved_to_billing_admin(self):
        from internal.routes.billing import router

        for path in ("/billing/saas/{saas_id}/clients", "/billing/saas/{saas_id}/clients/unbind"):
            route = next(route for route in router.routes if route.path == path)
            assert route.methods == {"POST"}

    def _render_detail(self, user, bindings):
        app = MagicMock(id="s1", is_active=True, description=None, webhook_url=None)
        app.name = _APP_NAME
        app.created_at = datetime(2024, 1, 1)
        return _render(
            "saas_detail.html",
            user=user,
            saas_app=app,
            products=[],
            customers=[],
            subscriptions=[],
            bindings=bindings,
            success=None,
            error=None,
        )

    def test_detail_template_shows_the_bindings_to_an_administrator(self):
        binding = MagicMock(client_id="client-a", created_at=datetime(2024, 1, 2, 3, 4))
        html = self._render_detail(_make_user(scopes=["billing:admin"]), [binding])
        assert "OAuth clients" in html
        assert "client-a" in html
        assert 'action="/billing/saas/s1/clients/unbind"' in html
        assert 'action="/billing/saas/s1/clients"' in html

    def test_detail_template_says_when_no_client_is_bound(self):
        html = self._render_detail(_make_user(scopes=["billing:admin"]), [])
        assert "No client bound yet." in html

    def test_detail_template_hides_the_bindings_without_the_admin_scope(self):
        html = self._render_detail(_make_user(scopes=["billing:read"]), [])
        assert "OAuth clients" not in html
        assert "/clients" not in html
