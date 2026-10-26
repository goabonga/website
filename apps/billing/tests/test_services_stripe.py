# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing.services.stripe_service.StripeService.

Mocks the entire stripe module to verify correct SDK calls and parameter passing.
"""

from unittest.mock import MagicMock, patch

import pytest
from billing.config import settings
from billing.services.stripe_service import (
    StripeService,
    build_stripe_description,
    get_stripe_service,
    tag_metadata,
    to_stripe_metadata,
)

# ---------------------------------------------------------------------------
# build_stripe_description
# ---------------------------------------------------------------------------


class TestBuildStripeDescription:
    """Tests for the build_stripe_description helper."""

    def test_description_only(self):
        result = build_stripe_description("A great product", None)
        assert result == "A great product"

    def test_features_only(self):
        extra = {"features": [{"label": "SSO"}, {"label": "API access"}]}
        result = build_stripe_description(None, extra)
        assert result == "Features:\n- SSO\n- API access"

    def test_description_and_features(self):
        extra = {"features": [{"label": "SSO"}, {"label": "API access"}]}
        result = build_stripe_description("Premium plan", extra)
        assert result == "Premium plan\n\nFeatures:\n- SSO\n- API access"

    def test_disabled_features_excluded(self):
        extra = {
            "features": [
                {"label": "SSO", "disabled": False},
                {"label": "Priority support", "disabled": True},
                {"label": "API access"},
            ]
        }
        result = build_stripe_description("Pro", extra)
        assert result == "Pro\n\nFeatures:\n- SSO\n- API access"

    def test_all_features_disabled(self):
        extra = {"features": [{"label": "X", "disabled": True}]}
        result = build_stripe_description("Basic", extra)
        assert result == "Basic"

    def test_empty_features_list(self):
        result = build_stripe_description("Plan", {"features": []})
        assert result == "Plan"

    def test_no_description_no_features(self):
        assert build_stripe_description(None, None) is None
        assert build_stripe_description(None, {}) is None
        assert build_stripe_description("", None) is None
        assert build_stripe_description("", {}) is None

    def test_feature_with_empty_label_skipped(self):
        extra = {"features": [{"label": ""}, {"label": "  "}, {"label": "Valid"}]}
        result = build_stripe_description(None, extra)
        assert result == "Features:\n- Valid"

    def test_non_dict_features_skipped(self):
        extra = {"features": ["just a string", {"label": "Real"}]}
        result = build_stripe_description(None, extra)
        assert result == "Features:\n- Real"

    def test_extra_data_without_features_key(self):
        result = build_stripe_description("Plan", {"limits": {"max": 10}})
        assert result == "Plan"

    def test_highlight_included(self):
        extra = {"features": [{"label": "SSO", "highlight": True}]}
        result = build_stripe_description(None, extra)
        assert result == "Features:\n- SSO"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """Clear get_stripe_service cache between tests."""
    get_stripe_service.cache_clear()
    yield
    get_stripe_service.cache_clear()


@pytest.fixture
def mock_stripe():
    """Patch the stripe module used inside stripe_service."""
    with patch("billing.services.stripe_service.stripe") as m:
        yield m


@pytest.fixture
def service(mock_stripe):
    """Return a StripeService instance with stripe already patched."""
    return StripeService()


# =========================================================================
# Products
# =========================================================================


class TestCreateProduct:
    """Tests for StripeService.create_product."""

    def test_create_product_all_params(self, service, mock_stripe):
        """All parameters provided including description and extra metadata."""
        mock_stripe.Product.create.return_value = MagicMock(id="prod_123")

        result = service.create_product(
            saas_id="saas_1",
            name="Premium Plan",
            description="The premium plan",
            metadata={"tier": "premium"},
        )

        mock_stripe.Product.create.assert_called_once_with(
            name="Premium Plan",
            metadata={"saas_id": "saas_1", "tier": "premium"},
            description="The premium plan",
        )
        assert result.id == "prod_123"

    def test_create_product_no_description(self, service, mock_stripe):
        """Description is None -- key should NOT appear in params."""
        mock_stripe.Product.create.return_value = MagicMock(id="prod_456")

        service.create_product(saas_id="saas_1", name="Basic Plan")

        call_kwargs = mock_stripe.Product.create.call_args[1]
        assert "description" not in call_kwargs
        assert call_kwargs["name"] == "Basic Plan"
        assert call_kwargs["metadata"] == {"saas_id": "saas_1"}

    def test_create_product_no_extra_metadata(self, service, mock_stripe):
        """metadata=None -- only saas_id should be in metadata."""
        mock_stripe.Product.create.return_value = MagicMock()

        service.create_product(saas_id="saas_2", name="Starter", metadata=None)

        call_kwargs = mock_stripe.Product.create.call_args[1]
        assert call_kwargs["metadata"] == {"saas_id": "saas_2"}

    def test_create_product_empty_metadata(self, service, mock_stripe):
        """metadata={} -- still only saas_id since empty dict is falsy."""
        mock_stripe.Product.create.return_value = MagicMock()

        service.create_product(saas_id="saas_3", name="Free", metadata={})

        call_kwargs = mock_stripe.Product.create.call_args[1]
        assert call_kwargs["metadata"] == {"saas_id": "saas_3"}


class TestUpdateProduct:
    """Tests for StripeService.update_product."""

    def test_update_product_all_params(self, service, mock_stripe):
        """All optional params provided."""
        mock_stripe.Product.modify.return_value = MagicMock(id="prod_1")

        result = service.update_product(
            stripe_product_id="prod_1",
            name="New Name",
            description="New desc",
            active=False,
            metadata={"key": "val"},
        )

        mock_stripe.Product.modify.assert_called_once_with(
            "prod_1",
            name="New Name",
            description="New desc",
            active=False,
            metadata={"key": "val"},
        )
        assert result.id == "prod_1"

    def test_update_product_no_optional_params(self, service, mock_stripe):
        """All optional params are None -- params dict should be empty."""
        mock_stripe.Product.modify.return_value = MagicMock()

        service.update_product(stripe_product_id="prod_2")

        mock_stripe.Product.modify.assert_called_once_with("prod_2")

    def test_update_product_partial_params(self, service, mock_stripe):
        """Only name provided."""
        mock_stripe.Product.modify.return_value = MagicMock()

        service.update_product(stripe_product_id="prod_3", name="Updated")

        mock_stripe.Product.modify.assert_called_once_with("prod_3", name="Updated")


class TestGetProduct:
    """Tests for StripeService.get_product."""

    def test_get_product(self, service, mock_stripe):
        mock_stripe.Product.retrieve.return_value = MagicMock(id="prod_99")

        result = service.get_product("prod_99")

        mock_stripe.Product.retrieve.assert_called_once_with("prod_99")
        assert result.id == "prod_99"


# =========================================================================
# Prices
# =========================================================================


class TestCreatePrice:
    """Tests for StripeService.create_price."""

    def test_create_price_recurring_licensed(self, service, mock_stripe):
        """Recurring licensed price with unit_amount."""
        mock_stripe.Price.create.return_value = MagicMock(id="price_1")

        result = service.create_price(
            saas_id="saas_1",
            stripe_product_id="prod_1",
            unit_amount=1999,
            currency="usd",
            billing_type="recurring",
            recurring_interval="month",
            recurring_interval_count=1,
            usage_type="licensed",
            nickname="Monthly Pro",
            metadata={"plan": "pro"},
        )

        call_kwargs = mock_stripe.Price.create.call_args[1]
        assert call_kwargs["product"] == "prod_1"
        assert call_kwargs["currency"] == "usd"
        assert call_kwargs["unit_amount"] == 1999
        assert call_kwargs["nickname"] == "Monthly Pro"
        assert call_kwargs["metadata"] == {"saas_id": "saas_1", "plan": "pro"}
        assert call_kwargs["recurring"] == {
            "interval": "month",
            "interval_count": 1,
            "usage_type": "licensed",
        }
        assert "aggregate_usage" not in call_kwargs["recurring"]
        assert result.id == "price_1"

    def test_create_price_recurring_metered(self, service, mock_stripe):
        """Recurring metered price -- no unit_amount, aggregate_usage=sum."""
        mock_stripe.Price.create.return_value = MagicMock(id="price_2")

        service.create_price(
            saas_id="saas_1",
            stripe_product_id="prod_1",
            unit_amount=None,
            currency="usd",
            billing_type="recurring",
            recurring_interval="month",
            recurring_interval_count=1,
            usage_type="metered",
        )

        call_kwargs = mock_stripe.Price.create.call_args[1]
        assert "unit_amount" not in call_kwargs
        assert call_kwargs["recurring"]["usage_type"] == "metered"
        assert call_kwargs["recurring"]["aggregate_usage"] == "sum"

    def test_create_price_one_time(self, service, mock_stripe):
        """One-time price -- no recurring, unit_amount present."""
        mock_stripe.Price.create.return_value = MagicMock(id="price_3")

        service.create_price(
            saas_id="saas_1",
            stripe_product_id="prod_1",
            unit_amount=5000,
            currency="eur",
            billing_type="one_time",
        )

        call_kwargs = mock_stripe.Price.create.call_args[1]
        assert call_kwargs["unit_amount"] == 5000
        assert call_kwargs["currency"] == "eur"
        assert "recurring" not in call_kwargs

    def test_create_price_no_nickname(self, service, mock_stripe):
        """nickname is None -- should not appear in params."""
        mock_stripe.Price.create.return_value = MagicMock()

        service.create_price(
            saas_id="saas_1",
            stripe_product_id="prod_1",
            unit_amount=1000,
            nickname=None,
        )

        call_kwargs = mock_stripe.Price.create.call_args[1]
        assert "nickname" not in call_kwargs

    def test_create_price_no_metadata(self, service, mock_stripe):
        """metadata=None -- only saas_id in metadata."""
        mock_stripe.Price.create.return_value = MagicMock()

        service.create_price(
            saas_id="saas_x",
            stripe_product_id="prod_1",
            unit_amount=500,
            metadata=None,
        )

        call_kwargs = mock_stripe.Price.create.call_args[1]
        assert call_kwargs["metadata"] == {"saas_id": "saas_x"}

    def test_create_price_recurring_defaults_to_month(self, service, mock_stripe):
        """recurring_interval=None should default to 'month'."""
        mock_stripe.Price.create.return_value = MagicMock()

        service.create_price(
            saas_id="saas_1",
            stripe_product_id="prod_1",
            unit_amount=100,
            billing_type="recurring",
            recurring_interval=None,
        )

        call_kwargs = mock_stripe.Price.create.call_args[1]
        assert call_kwargs["recurring"]["interval"] == "month"


class TestGetPrice:
    """Tests for StripeService.get_price."""

    def test_get_price(self, service, mock_stripe):
        mock_stripe.Price.retrieve.return_value = MagicMock(id="price_42")

        result = service.get_price("price_42")

        mock_stripe.Price.retrieve.assert_called_once_with("price_42")
        assert result.id == "price_42"


class TestUpdatePrice:
    """Tests for StripeService.update_price."""

    def test_update_price_all_params(self, service, mock_stripe):
        mock_stripe.Price.modify.return_value = MagicMock(id="price_1")

        result = service.update_price(
            stripe_price_id="price_1",
            nickname="Updated",
            active=False,
            metadata={"extra": "data"},
        )

        mock_stripe.Price.modify.assert_called_once_with(
            "price_1",
            nickname="Updated",
            active=False,
            metadata={"extra": "data"},
        )
        assert result.id == "price_1"

    def test_update_price_no_params(self, service, mock_stripe):
        """No optional params -- empty params dict."""
        mock_stripe.Price.modify.return_value = MagicMock()

        service.update_price(stripe_price_id="price_2")

        mock_stripe.Price.modify.assert_called_once_with("price_2")

    def test_update_price_partial(self, service, mock_stripe):
        """Only nickname provided."""
        mock_stripe.Price.modify.return_value = MagicMock()

        service.update_price(stripe_price_id="price_3", nickname="New Name")

        mock_stripe.Price.modify.assert_called_once_with("price_3", nickname="New Name")


# =========================================================================
# Customers
# =========================================================================


class TestCreateCustomer:
    """Tests for StripeService.create_customer."""

    def test_create_customer_all_params(self, service, mock_stripe):
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_1")

        result = service.create_customer(
            saas_id="saas_1",
            email="user@test.com",
            name="John Doe",
            external_id="ext_123",
            metadata={"role": "admin"},
        )

        call_kwargs = mock_stripe.Customer.create.call_args[1]
        assert call_kwargs["email"] == "user@test.com"
        assert call_kwargs["name"] == "John Doe"
        assert call_kwargs["metadata"] == {
            "saas_id": "saas_1",
            "external_id": "ext_123",
            "role": "admin",
        }
        assert result.id == "cus_1"

    def test_create_customer_name_none(self, service, mock_stripe):
        """name=None -- key should NOT appear in params."""
        mock_stripe.Customer.create.return_value = MagicMock()

        service.create_customer(saas_id="saas_1", email="a@b.com")

        call_kwargs = mock_stripe.Customer.create.call_args[1]
        assert "name" not in call_kwargs
        assert call_kwargs["email"] == "a@b.com"

    def test_create_customer_no_external_id(self, service, mock_stripe):
        """external_id=None -- should not appear in metadata."""
        mock_stripe.Customer.create.return_value = MagicMock()

        service.create_customer(saas_id="saas_1", email="x@y.com")

        call_kwargs = mock_stripe.Customer.create.call_args[1]
        assert "external_id" not in call_kwargs["metadata"]

    def test_create_customer_no_metadata(self, service, mock_stripe):
        """metadata=None -- only saas_id in metadata."""
        mock_stripe.Customer.create.return_value = MagicMock()

        service.create_customer(saas_id="saas_2", email="z@w.com", metadata=None)

        call_kwargs = mock_stripe.Customer.create.call_args[1]
        assert call_kwargs["metadata"] == {"saas_id": "saas_2"}


class TestUpdateCustomer:
    """Tests for StripeService.update_customer."""

    def test_update_customer_all_params(self, service, mock_stripe):
        mock_stripe.Customer.modify.return_value = MagicMock(id="cus_1")

        result = service.update_customer(
            stripe_customer_id="cus_1",
            email="new@test.com",
            name="Jane Doe",
            metadata={"key": "val"},
        )

        mock_stripe.Customer.modify.assert_called_once_with(
            "cus_1",
            email="new@test.com",
            name="Jane Doe",
            metadata={"key": "val"},
        )
        assert result.id == "cus_1"

    def test_update_customer_no_params(self, service, mock_stripe):
        mock_stripe.Customer.modify.return_value = MagicMock()

        service.update_customer(stripe_customer_id="cus_2")

        mock_stripe.Customer.modify.assert_called_once_with("cus_2")

    def test_update_customer_partial(self, service, mock_stripe):
        """Only email provided."""
        mock_stripe.Customer.modify.return_value = MagicMock()

        service.update_customer(stripe_customer_id="cus_3", email="a@b.com")

        mock_stripe.Customer.modify.assert_called_once_with("cus_3", email="a@b.com")


class TestGetCustomer:
    """Tests for StripeService.get_customer."""

    def test_get_customer(self, service, mock_stripe):
        mock_stripe.Customer.retrieve.return_value = MagicMock(id="cus_99")

        result = service.get_customer("cus_99")

        mock_stripe.Customer.retrieve.assert_called_once_with("cus_99")
        assert result.id == "cus_99"


class TestCreateCustomerPortalSession:
    """Tests for StripeService.create_customer_portal_session."""

    def test_create_portal_session(self, service, mock_stripe):
        mock_stripe.billing_portal.Session.create.return_value = MagicMock(
            url="https://portal.stripe.com/sess_1"
        )

        result = service.create_customer_portal_session(
            stripe_customer_id="cus_1",
            return_url="https://app.example.com/billing",
        )

        mock_stripe.billing_portal.Session.create.assert_called_once_with(
            customer="cus_1",
            return_url="https://app.example.com/billing",
        )
        assert result.url == "https://portal.stripe.com/sess_1"


# =========================================================================
# Subscriptions
# =========================================================================


class TestCreateSubscription:
    """Tests for StripeService.create_subscription."""

    def test_create_subscription_all_params(self, service, mock_stripe):
        mock_stripe.Subscription.create.return_value = MagicMock(id="sub_1")

        result = service.create_subscription(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            trial_period_days=14,
            metadata={"source": "checkout"},
        )

        call_kwargs = mock_stripe.Subscription.create.call_args[1]
        assert call_kwargs["customer"] == "cus_1"
        assert call_kwargs["items"] == [{"price": "price_1"}]
        assert call_kwargs["trial_period_days"] == 14
        assert call_kwargs["metadata"] == {
            "saas_id": "saas_1",
            "source": "checkout",
        }
        assert result.id == "sub_1"

    def test_create_subscription_no_trial(self, service, mock_stripe):
        """trial_period_days=None -- key should NOT appear in params."""
        mock_stripe.Subscription.create.return_value = MagicMock()

        service.create_subscription(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
        )

        call_kwargs = mock_stripe.Subscription.create.call_args[1]
        assert "trial_period_days" not in call_kwargs

    def test_create_subscription_trial_zero(self, service, mock_stripe):
        """trial_period_days=0 -- falsy, should NOT appear in params."""
        mock_stripe.Subscription.create.return_value = MagicMock()

        service.create_subscription(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            trial_period_days=0,
        )

        call_kwargs = mock_stripe.Subscription.create.call_args[1]
        assert "trial_period_days" not in call_kwargs

    def test_create_subscription_no_extra_metadata(self, service, mock_stripe):
        """metadata=None -- only saas_id in metadata."""
        mock_stripe.Subscription.create.return_value = MagicMock()

        service.create_subscription(
            saas_id="saas_x",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
        )

        call_kwargs = mock_stripe.Subscription.create.call_args[1]
        assert call_kwargs["metadata"] == {"saas_id": "saas_x"}


class TestUpdateSubscription:
    """Tests for StripeService.update_subscription."""

    def test_update_subscription_all_params(self, service, mock_stripe):
        mock_stripe.Subscription.modify.return_value = MagicMock(id="sub_1")

        result = service.update_subscription(
            stripe_subscription_id="sub_1",
            cancel_at_period_end=True,
            metadata={"reason": "downgrade"},
        )

        mock_stripe.Subscription.modify.assert_called_once_with(
            "sub_1",
            cancel_at_period_end=True,
            metadata={"reason": "downgrade"},
        )
        assert result.id == "sub_1"

    def test_update_subscription_no_params(self, service, mock_stripe):
        mock_stripe.Subscription.modify.return_value = MagicMock()

        service.update_subscription(stripe_subscription_id="sub_2")

        mock_stripe.Subscription.modify.assert_called_once_with("sub_2")


class TestCancelSubscription:
    """Tests for StripeService.cancel_subscription."""

    def test_cancel_immediately(self, service, mock_stripe):
        """immediately=True should call stripe.Subscription.cancel."""
        mock_stripe.Subscription.cancel.return_value = MagicMock(id="sub_1", status="canceled")

        result = service.cancel_subscription("sub_1", immediately=True)

        mock_stripe.Subscription.cancel.assert_called_once_with("sub_1")
        mock_stripe.Subscription.modify.assert_not_called()
        assert result.status == "canceled"

    def test_cancel_at_period_end(self, service, mock_stripe):
        """immediately=False should call stripe.Subscription.modify."""
        mock_stripe.Subscription.modify.return_value = MagicMock(
            id="sub_2", cancel_at_period_end=True
        )

        result = service.cancel_subscription("sub_2", immediately=False)

        mock_stripe.Subscription.modify.assert_called_once_with("sub_2", cancel_at_period_end=True)
        mock_stripe.Subscription.cancel.assert_not_called()
        assert result.cancel_at_period_end is True

    def test_cancel_default_is_at_period_end(self, service, mock_stripe):
        """Default immediately=False."""
        mock_stripe.Subscription.modify.return_value = MagicMock()

        service.cancel_subscription("sub_3")

        mock_stripe.Subscription.modify.assert_called_once_with("sub_3", cancel_at_period_end=True)
        mock_stripe.Subscription.cancel.assert_not_called()


class TestGetSubscription:
    """Tests for StripeService.get_subscription."""

    def test_get_subscription(self, service, mock_stripe):
        mock_stripe.Subscription.retrieve.return_value = MagicMock(id="sub_99")

        result = service.get_subscription("sub_99")

        mock_stripe.Subscription.retrieve.assert_called_once_with("sub_99")
        assert result.id == "sub_99"


class TestPreviewSubscriptionUpgrade:
    """Tests for StripeService.preview_subscription_upgrade."""

    def test_preview_upgrade(self, service, mock_stripe):
        """Happy path: subscription with items."""
        # Build a mock subscription with bracket-notation access for items
        mock_item = MagicMock(id="si_item_1")
        mock_items_data = MagicMock()
        mock_items_data.data = [mock_item]

        mock_sub = MagicMock()
        mock_sub.__getitem__ = lambda self_mock, key: mock_items_data if key == "items" else None
        mock_sub.customer = "cus_1"

        mock_stripe.Subscription.retrieve.return_value = mock_sub
        mock_stripe.Invoice.create_preview.return_value = MagicMock(id="inv_preview")

        result = service.preview_subscription_upgrade("sub_1", "price_new")

        mock_stripe.Subscription.retrieve.assert_called_once_with("sub_1")
        mock_stripe.Invoice.create_preview.assert_called_once_with(
            customer="cus_1",
            subscription="sub_1",
            subscription_details={
                "items": [
                    {
                        "id": "si_item_1",
                        "price": "price_new",
                    }
                ],
                "proration_behavior": "create_prorations",
            },
        )
        assert result.id == "inv_preview"

    def test_preview_upgrade_no_items_raises(self, service, mock_stripe):
        """Subscription with empty items should raise ValueError."""
        mock_items_data = MagicMock()
        mock_items_data.data = []

        mock_sub = MagicMock()
        mock_sub.__getitem__ = lambda self_mock, key: mock_items_data if key == "items" else None

        mock_stripe.Subscription.retrieve.return_value = mock_sub

        with pytest.raises(ValueError, match="Subscription has no items"):
            service.preview_subscription_upgrade("sub_1", "price_new")

    def test_preview_upgrade_none_items_raises(self, service, mock_stripe):
        """Subscription with None items should raise ValueError."""
        mock_sub = MagicMock()
        mock_sub.__getitem__ = lambda self_mock, key: None if key == "items" else None

        mock_stripe.Subscription.retrieve.return_value = mock_sub

        with pytest.raises(ValueError, match="Subscription has no items"):
            service.preview_subscription_upgrade("sub_1", "price_new")


class TestUpgradeSubscription:
    """Tests for StripeService.upgrade_subscription."""

    def _make_subscription_mock(self, mock_stripe):
        """Helper: create a mock subscription with items."""
        mock_item = MagicMock(id="si_item_1")
        mock_items_data = MagicMock()
        mock_items_data.data = [mock_item]

        mock_sub = MagicMock()
        mock_sub.__getitem__ = lambda self_mock, key: mock_items_data if key == "items" else None
        mock_sub.customer = "cus_1"

        mock_stripe.Subscription.retrieve.return_value = mock_sub
        return mock_sub

    def test_upgrade_with_always_invoice(self, service, mock_stripe):
        """proration_behavior='always_invoice' should fetch the latest invoice."""
        self._make_subscription_mock(mock_stripe)

        updated_sub = MagicMock(id="sub_updated")
        mock_stripe.Subscription.modify.return_value = updated_sub

        mock_invoice = MagicMock(id="inv_1")
        mock_invoice_list = MagicMock()
        mock_invoice_list.data = [mock_invoice]
        mock_stripe.Invoice.list.return_value = mock_invoice_list

        sub, invoice = service.upgrade_subscription(
            stripe_subscription_id="sub_1",
            new_stripe_price_id="price_new",
            proration_behavior="always_invoice",
        )

        mock_stripe.Subscription.modify.assert_called_once_with(
            "sub_1",
            items=[{"id": "si_item_1", "price": "price_new"}],
            proration_behavior="always_invoice",
        )
        mock_stripe.Invoice.list.assert_called_once_with(subscription="sub_1", limit=1)
        assert sub.id == "sub_updated"
        assert invoice.id == "inv_1"

    def test_upgrade_create_prorations_no_invoice(self, service, mock_stripe):
        """proration_behavior='create_prorations' should return None invoice."""
        self._make_subscription_mock(mock_stripe)

        updated_sub = MagicMock(id="sub_updated")
        mock_stripe.Subscription.modify.return_value = updated_sub

        sub, invoice = service.upgrade_subscription(
            stripe_subscription_id="sub_1",
            new_stripe_price_id="price_new",
            proration_behavior="create_prorations",
        )

        mock_stripe.Invoice.list.assert_not_called()
        assert sub.id == "sub_updated"
        assert invoice is None

    def test_upgrade_default_proration_behavior(self, service, mock_stripe):
        """Default proration_behavior should be 'create_prorations'."""
        self._make_subscription_mock(mock_stripe)
        mock_stripe.Subscription.modify.return_value = MagicMock()

        sub, invoice = service.upgrade_subscription(
            stripe_subscription_id="sub_1",
            new_stripe_price_id="price_new",
        )

        call_kwargs = mock_stripe.Subscription.modify.call_args[1]
        assert call_kwargs["proration_behavior"] == "create_prorations"
        assert invoice is None

    def test_upgrade_always_invoice_empty_list(self, service, mock_stripe):
        """always_invoice but no invoices found -- invoice should be None."""
        self._make_subscription_mock(mock_stripe)
        mock_stripe.Subscription.modify.return_value = MagicMock()

        mock_invoice_list = MagicMock()
        mock_invoice_list.data = []
        mock_stripe.Invoice.list.return_value = mock_invoice_list

        sub, invoice = service.upgrade_subscription(
            stripe_subscription_id="sub_1",
            new_stripe_price_id="price_new",
            proration_behavior="always_invoice",
        )

        assert invoice is None

    def test_upgrade_always_invoice_fetch_error(self, service, mock_stripe):
        """always_invoice but invoice fetch raises -- should log warning, return None."""
        self._make_subscription_mock(mock_stripe)
        mock_stripe.Subscription.modify.return_value = MagicMock(id="sub_updated")
        mock_stripe.Invoice.list.side_effect = Exception("Stripe API error")

        sub, invoice = service.upgrade_subscription(
            stripe_subscription_id="sub_1",
            new_stripe_price_id="price_new",
            proration_behavior="always_invoice",
        )

        assert sub.id == "sub_updated"
        assert invoice is None

    def test_upgrade_no_items_raises(self, service, mock_stripe):
        """Subscription with no items should raise ValueError."""
        mock_items_data = MagicMock()
        mock_items_data.data = []
        mock_sub = MagicMock()
        mock_sub.__getitem__ = lambda self_mock, key: mock_items_data if key == "items" else None
        mock_stripe.Subscription.retrieve.return_value = mock_sub

        with pytest.raises(ValueError, match="Subscription has no items"):
            service.upgrade_subscription("sub_1", "price_new")


# =========================================================================
# Checkout Sessions
# =========================================================================


class TestCreateCheckoutSession:
    """Tests for StripeService.create_checkout_session."""

    def test_subscription_mode_all_params(self, service, mock_stripe):
        """subscription mode with trial and metadata."""
        mock_stripe.checkout.Session.create.return_value = MagicMock(id="cs_1")

        result = service.create_checkout_session(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
            mode="subscription",
            quantity=1,
            trial_period_days=7,
            metadata={"campaign": "spring"},
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs["customer"] == "cus_1"
        assert call_kwargs["line_items"] == [{"price": "price_1", "quantity": 1}]
        assert call_kwargs["mode"] == "subscription"
        assert call_kwargs["success_url"] == "https://app.example.com/success"
        assert call_kwargs["cancel_url"] == "https://app.example.com/cancel"
        assert call_kwargs["metadata"] == {
            "saas_id": "saas_1",
            "campaign": "spring",
        }
        assert call_kwargs["subscription_data"] == {
            "metadata": {"saas_id": "saas_1"},
            "trial_period_days": 7,
        }
        assert result.id == "cs_1"

    def test_subscription_mode_no_trial(self, service, mock_stripe):
        """subscription mode without trial -- trial_period_days should not be in subscription_data."""
        mock_stripe.checkout.Session.create.return_value = MagicMock()

        service.create_checkout_session(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            success_url="https://ok.com",
            cancel_url="https://cancel.com",
            mode="subscription",
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs["subscription_data"] == {
            "metadata": {"saas_id": "saas_1"},
        }
        assert "trial_period_days" not in call_kwargs["subscription_data"]

    def test_payment_mode(self, service, mock_stripe):
        """payment mode -- no subscription_data at all."""
        mock_stripe.checkout.Session.create.return_value = MagicMock()

        service.create_checkout_session(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            success_url="https://ok.com",
            cancel_url="https://cancel.com",
            mode="payment",
            quantity=3,
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs["mode"] == "payment"
        assert call_kwargs["line_items"] == [{"price": "price_1", "quantity": 3}]
        assert "subscription_data" not in call_kwargs

    def test_subscription_mode_trial_zero(self, service, mock_stripe):
        """trial_period_days=0 is falsy -- should not appear in subscription_data."""
        mock_stripe.checkout.Session.create.return_value = MagicMock()

        service.create_checkout_session(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            success_url="https://ok.com",
            cancel_url="https://cancel.com",
            mode="subscription",
            trial_period_days=0,
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert "trial_period_days" not in call_kwargs["subscription_data"]


# =========================================================================
# Usage Records
# =========================================================================


class TestReportUsage:
    """Tests for StripeService.report_usage."""

    def test_report_usage_all_params(self, service, mock_stripe):
        mock_stripe.SubscriptionItem.create_usage_record.return_value = MagicMock(id="mbur_1")

        result = service.report_usage(
            stripe_subscription_item_id="si_item_1",
            quantity=100,
            timestamp=1700000000,
            idempotency_key="idem_key_1",
        )

        mock_stripe.SubscriptionItem.create_usage_record.assert_called_once_with(
            "si_item_1",
            quantity=100,
            action="increment",
            timestamp=1700000000,
            idempotency_key="idem_key_1",
        )
        assert result.id == "mbur_1"

    def test_report_usage_default_timestamp(self, service, mock_stripe):
        """timestamp=None -- defaults to current time."""
        mock_stripe.SubscriptionItem.create_usage_record.return_value = MagicMock()

        with patch("billing.services.stripe_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value.timestamp.return_value = 1700001234.5
            service.report_usage(
                stripe_subscription_item_id="si_item_1",
                quantity=50,
            )

        call_kwargs = mock_stripe.SubscriptionItem.create_usage_record.call_args
        # Positional args
        assert call_kwargs[0] == ("si_item_1",)
        # Keyword args
        assert call_kwargs[1]["quantity"] == 50
        assert call_kwargs[1]["action"] == "increment"
        assert call_kwargs[1]["timestamp"] == 1700001234
        assert "idempotency_key" not in call_kwargs[1]

    def test_report_usage_no_idempotency_key(self, service, mock_stripe):
        """idempotency_key=None -- should not appear in kwargs."""
        mock_stripe.SubscriptionItem.create_usage_record.return_value = MagicMock()

        service.report_usage(
            stripe_subscription_item_id="si_item_1",
            quantity=10,
            timestamp=1700000000,
        )

        call_kwargs = mock_stripe.SubscriptionItem.create_usage_record.call_args[1]
        assert "idempotency_key" not in call_kwargs


# =========================================================================
# Webhook Signature Verification
# =========================================================================


class TestVerifyWebhookSignature:
    """Tests for StripeService.verify_webhook_signature."""

    def test_verify_with_explicit_secret(self, service, mock_stripe):
        mock_stripe.Webhook.construct_event.return_value = MagicMock(type="test.event")

        result = service.verify_webhook_signature(
            payload=b'{"test": true}',
            signature="sig_1",
            webhook_secret="whsec_explicit",
        )

        mock_stripe.Webhook.construct_event.assert_called_once_with(
            b'{"test": true}', "sig_1", "whsec_explicit"
        )
        assert result.type == "test.event"

    def test_verify_with_default_secret(self, service, mock_stripe):
        """webhook_secret=None should fallback to settings.stripe_webhook_secret."""
        mock_stripe.Webhook.construct_event.return_value = MagicMock()

        with patch("billing.services.stripe_service.settings") as mock_settings:
            mock_settings.stripe_webhook_secret = "whsec_default"

            service.verify_webhook_signature(
                payload=b"body",
                signature="sig_2",
                webhook_secret=None,
            )

        mock_stripe.Webhook.construct_event.assert_called_once_with(
            b"body", "sig_2", "whsec_default"
        )


# =========================================================================
# get_stripe_service (lru_cache)
# =========================================================================


class TestGetStripeService:
    """Tests for the get_stripe_service() factory."""

    def test_returns_stripe_service_instance(self, mock_stripe):
        svc = get_stripe_service()
        assert isinstance(svc, StripeService)

    def test_is_cached(self, mock_stripe):
        svc1 = get_stripe_service()
        svc2 = get_stripe_service()
        assert svc1 is svc2


# =========================================================================
# Metadata handling
# =========================================================================


class TestToStripeMetadata:
    """Stripe only accepts flat string metadata."""

    def test_strings_are_kept(self):
        assert to_stripe_metadata({"tier": "pro"}) == {"tier": "pro"}

    def test_scalars_are_stringified(self):
        result = to_stripe_metadata({"seats": 5, "beta": True, "ratio": 1.5})

        assert result == {"seats": "5", "beta": "true", "ratio": "1.5"}

    def test_nested_values_are_serialized_to_compact_json(self):
        """features / limits documents are sent as JSON strings, not nested objects."""
        result = to_stripe_metadata(
            {"limits": {"b": 2, "a": 1}, "features": [{"label": "x"}]},
        )

        assert result == {"limits": '{"a":1,"b":2}', "features": '[{"label":"x"}]'}
        assert all(isinstance(value, str) for value in result.values())

    def test_none_values_are_dropped(self):
        assert to_stripe_metadata({"a": None, "b": "1"}) == {"b": "1"}

    def test_none_and_empty_metadata(self):
        assert to_stripe_metadata(None) == {}
        assert to_stripe_metadata({}) == {}

    def test_server_owned_keys_are_dropped(self):
        result = to_stripe_metadata({"saas_id": "evil", "external_id": "evil", "ok": "1"})

        assert result == {"ok": "1"}

    def test_extra_reserved_keys_are_dropped(self):
        assert to_stripe_metadata({"a": "1", "b": "2"}, reserved={"a"}) == {"b": "2"}

    def test_oversized_entries_are_skipped(self):
        with patch("billing.services.stripe_service.logger") as log:
            result = to_stripe_metadata({"k" * 41: "x", "big": "y" * 501, "fine": "z"})

        assert result == {"fine": "z"}
        assert log.warning.call_count == 2

    def test_key_count_is_capped_below_the_stripe_limit(self):
        """One slot stays free for the server-owned saas_id."""
        result = to_stripe_metadata({f"k{i}": "v" for i in range(80)})

        assert len(result) == 49


class TestTagMetadata:
    """The server-owned values always win over caller metadata."""

    def test_saas_id_is_always_set(self):
        assert tag_metadata("saas_1") == {"saas_id": "saas_1"}

    def test_caller_cannot_override_saas_id(self):
        assert tag_metadata("saas_1", {"saas_id": "other", "a": "1"}) == {
            "saas_id": "saas_1",
            "a": "1",
        }

    def test_owned_values_win(self):
        result = tag_metadata("saas_1", {"external_id": "forged"}, external_id="user-1")

        assert result == {"saas_id": "saas_1", "external_id": "user-1"}

    def test_empty_owned_values_are_omitted(self):
        assert tag_metadata("saas_1", None, external_id="") == {"saas_id": "saas_1"}


class TestMetadataSentToStripe:
    """Every create and update call sends sanitized metadata."""

    def test_checkout_metadata_cannot_override_saas_id(self, service, mock_stripe):
        service.create_checkout_session(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            success_url="https://app.example.test/ok",
            cancel_url="https://app.example.test/ko",
            metadata={"saas_id": "forged", "campaign": "spring", "nested": {"a": 1}},
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs["metadata"] == {
            "saas_id": "saas_1",
            "campaign": "spring",
            "nested": '{"a":1}',
        }
        assert call_kwargs["subscription_data"]["metadata"] == {"saas_id": "saas_1"}

    def test_checkout_branding_options_are_forwarded(self, service, mock_stripe):
        service.create_checkout_session(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            success_url="https://app.example.test/ok",
            cancel_url="https://app.example.test/ko",
            locale="fr",
            custom_text={"submit": {"message": "Thanks"}},
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs["locale"] == "fr"
        assert call_kwargs["custom_text"] == {"submit": {"message": "Thanks"}}

    def test_checkout_without_branding_sends_no_locale(self, service, mock_stripe):
        service.create_checkout_session(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            success_url="https://app.example.test/ok",
            cancel_url="https://app.example.test/ko",
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert "locale" not in call_kwargs
        assert "custom_text" not in call_kwargs

    def test_product_nested_metadata_is_stringified(self, service, mock_stripe):
        service.create_product(
            saas_id="saas_1",
            name="Pro",
            metadata={"limits": {"seats": 5}, "features": [{"label": "A"}], "saas_id": "x"},
        )

        metadata = mock_stripe.Product.create.call_args[1]["metadata"]
        assert metadata == {
            "saas_id": "saas_1",
            "limits": '{"seats":5}',
            "features": '[{"label":"A"}]',
        }

    def test_customer_external_id_and_saas_id_cannot_be_forged(self, service, mock_stripe):
        service.create_customer(
            saas_id="saas_1",
            email="a@example.test",
            external_id="user-1",
            metadata={"saas_id": "x", "external_id": "y"},
        )

        metadata = mock_stripe.Customer.create.call_args[1]["metadata"]
        assert metadata == {"saas_id": "saas_1", "external_id": "user-1"}

    def test_subscription_and_price_metadata_are_tagged(self, service, mock_stripe):
        service.create_subscription(
            saas_id="saas_1",
            stripe_customer_id="cus_1",
            stripe_price_id="price_1",
            metadata={"saas_id": "x"},
        )
        service.create_price(
            saas_id="saas_1",
            stripe_product_id="prod_1",
            unit_amount=100,
            metadata={"saas_id": "x"},
        )

        assert mock_stripe.Subscription.create.call_args[1]["metadata"] == {"saas_id": "saas_1"}
        assert mock_stripe.Price.create.call_args[1]["metadata"] == {"saas_id": "saas_1"}

    def test_updates_cannot_rewrite_saas_id(self, service, mock_stripe):
        service.update_product("prod_1", metadata={"saas_id": "x", "n": {"a": 1}})
        service.update_price("price_1", metadata={"saas_id": "x"})
        service.update_customer("cus_1", metadata={"saas_id": "x", "external_id": "y"})
        service.update_subscription("sub_1", metadata={"saas_id": "x", "a": 1})

        assert mock_stripe.Product.modify.call_args[1]["metadata"] == {"n": '{"a":1}'}
        assert mock_stripe.Price.modify.call_args[1]["metadata"] == {}
        assert mock_stripe.Customer.modify.call_args[1]["metadata"] == {}
        assert mock_stripe.Subscription.modify.call_args[1]["metadata"] == {"a": "1"}


class TestCatalogDefaults:
    """Currency and recurring interval defaults come from the settings."""

    def test_default_currency_and_interval_are_read_from_settings(
        self, service, mock_stripe, monkeypatch
    ):
        monkeypatch.setattr(settings, "default_currency", "eur")
        monkeypatch.setattr(settings, "default_recurring_interval", "year")

        service.create_price(saas_id="saas_1", stripe_product_id="prod_1", unit_amount=100)

        params = mock_stripe.Price.create.call_args[1]
        assert params["currency"] == "eur"
        assert params["recurring"]["interval"] == "year"

    def test_explicit_values_win_over_the_defaults(self, service, mock_stripe):
        service.create_price(
            saas_id="saas_1",
            stripe_product_id="prod_1",
            unit_amount=100,
            currency="chf",
            recurring_interval="week",
        )

        params = mock_stripe.Price.create.call_args[1]
        assert params["currency"] == "chf"
        assert params["recurring"]["interval"] == "week"
