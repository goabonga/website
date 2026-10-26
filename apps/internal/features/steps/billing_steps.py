# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for billing feature tests.

Uses MagicMock objects to simulate Pydantic models returned by billing_client.
All billing_client methods are async, so we configure return_value on the mock
(MagicMock auto-handles awaiting).
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from behave import given, then

# ---------------------------------------------------------------------------
# Mock factory helpers
# ---------------------------------------------------------------------------


def _make_saas_app(**kwargs):
    """Create a mock SaaS app object with attribute access."""
    app = MagicMock()
    app.id = kwargs.get("id", "saas-1")
    app.name = kwargs.get("name", "Test App")
    app.slug = kwargs.get("slug", "test-app")
    app.description = kwargs.get("description", "A test app")
    app.is_active = kwargs.get("is_active", True)
    app.webhook_url = kwargs.get("webhook_url", "")
    app.webhook_secret = kwargs.get("webhook_secret", "")
    app.branding = kwargs.get("branding")
    app.checkout_url_allowlist = kwargs.get("checkout_url_allowlist")
    app.stripe_connected = kwargs.get("stripe_connected", False)
    app.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    app.products = kwargs.get("products", [])
    return app


def _make_product(**kwargs):
    """Create a mock product object."""
    product = MagicMock()
    product.id = kwargs.get("id", "prod-1")
    product.name = kwargs.get("name", "Test Product")
    product.description = kwargs.get("description", "A test product")
    product.slug = kwargs.get("slug", "test-product")
    product.stripe_product_id = kwargs.get("stripe_product_id", "stripe_prod_123")
    product.is_active = kwargs.get("is_active", True)
    product.sort_order = kwargs.get("sort_order", 0)
    product.default_trial_days = kwargs.get("default_trial_days", 0)
    product.is_recommended = kwargs.get("is_recommended", False)
    product.features = kwargs.get("features", [])
    product.limits = kwargs.get("limits", {})
    product.metadata = kwargs.get("metadata", {})
    product.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    # extra_data is used by product_detail.html template for nested fields
    extra_data = MagicMock()
    extra_defaults = kwargs.get("extra_data", {})
    extra_data.slug = extra_defaults.get("slug", "test-product")
    extra_data.is_recommended = extra_defaults.get("is_recommended", False)
    extra_data.sort_order = extra_defaults.get("sort_order", 0)
    extra_data.default_trial_days = extra_defaults.get("default_trial_days", 0)
    extra_data.features = extra_defaults.get(
        "features",
        [{"label": "Feature 1", "highlight": False, "disabled": False}],
    )
    extra_data.limits = extra_defaults.get("limits", {"max_users": 10})
    product.extra_data = extra_data
    return product


def _make_price(**kwargs):
    """Create a mock price object."""
    price = MagicMock()
    price.id = kwargs.get("id", "price-1")
    price.stripe_price_id = kwargs.get("stripe_price_id", "stripe_price_123")
    price.unit_amount = kwargs.get("unit_amount", 1999)
    price.currency = kwargs.get("currency", "eur")
    price.billing_type = kwargs.get("billing_type", "recurring")
    price.recurring_interval = kwargs.get("recurring_interval", "month")
    price.recurring_interval_count = kwargs.get("recurring_interval_count", 1)
    price.usage_type = kwargs.get("usage_type", "licensed")
    price.nickname = kwargs.get("nickname", "Monthly")
    price.is_active = kwargs.get("is_active", True)
    price.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    return price


def _make_customer(**kwargs):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = kwargs.get("id", "cust-1")
    customer.email = kwargs.get("email", "customer@example.com")
    customer.name = kwargs.get("name", "Test Customer")
    customer.stripe_customer_id = kwargs.get("stripe_customer_id", "stripe_cus_123")
    customer.external_id = kwargs.get("external_id", "ext-cust-001")
    customer.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    return customer


def _make_subscription(**kwargs):
    """Create a mock subscription object."""
    sub = MagicMock()
    sub.id = kwargs.get("id", "sub-1")
    sub.customer_id = kwargs.get("customer_id", "cust-1")
    sub.stripe_subscription_id = kwargs.get("stripe_subscription_id", "stripe_sub_123")
    sub.status = kwargs.get("status", "active")
    sub.current_period_start = kwargs.get("current_period_start", datetime(2024, 1, 1))
    sub.current_period_end = kwargs.get("current_period_end", datetime(2024, 2, 1))
    sub.cancel_at_period_end = kwargs.get("cancel_at_period_end", False)
    sub.canceled_at = kwargs.get("canceled_at")
    sub.stripe_subscription_item_id = kwargs.get("stripe_subscription_item_id", "stripe_si_123")
    sub.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    return sub


def _make_portal(**kwargs):
    """Create a mock customer portal object."""
    portal = MagicMock()
    portal.url = kwargs.get("url", "https://billing.stripe.com/portal/session_123")
    return portal


# ---------------------------------------------------------------------------
# Dashboard steps
# ---------------------------------------------------------------------------


@given("the billing SaaS apps list returns data")
def step_billing_saas_list(context):
    mock = context.mock_billing
    mock.list_saas_apps = AsyncMock(return_value=[_make_saas_app()])


# ---------------------------------------------------------------------------
# SaaS app steps
# ---------------------------------------------------------------------------


@given('a SaaS app exists with id "{saas_id}"')
def step_saas_exists(context, saas_id):
    mock = context.mock_billing
    saas_app = _make_saas_app(id=saas_id)
    mock.get_saas_app = AsyncMock(return_value=saas_app)
    # Always set up default empty lists for related data used in detail view
    mock.list_products = AsyncMock(return_value=[])
    mock.list_customers = AsyncMock(return_value=[])
    mock.list_subscriptions = AsyncMock(return_value=[])


@given("a SaaS app does not exist")
def step_saas_not_exists(context):
    mock = context.mock_billing
    mock.get_saas_app = AsyncMock(return_value=None)
    mock.get_product = AsyncMock(return_value=None)


@given("creating a SaaS app succeeds")
def step_create_saas_succeeds(context):
    mock = context.mock_billing
    mock.create_saas_app = AsyncMock(return_value=_make_saas_app(id="saas-new"))


@given("creating a SaaS app fails")
def step_create_saas_fails(context):
    mock = context.mock_billing
    mock.create_saas_app = AsyncMock(return_value=None)


@given("updating a SaaS app succeeds")
def step_update_saas_succeeds(context):
    mock = context.mock_billing
    mock.update_saas_app = AsyncMock(return_value=_make_saas_app())


@given("updating a SaaS app fails")
def step_update_saas_fails(context):
    mock = context.mock_billing
    mock.update_saas_app = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Product steps
# ---------------------------------------------------------------------------


@given('the billing products list returns data for SaaS "{saas_id}"')
def step_products_list(context, saas_id):
    mock = context.mock_billing
    mock.list_products = AsyncMock(return_value=[_make_product()])


@given('a billing product exists with id "{product_id}" for SaaS "{saas_id}"')
def step_product_exists(context, product_id, saas_id):
    mock = context.mock_billing
    mock.get_product = AsyncMock(return_value=_make_product(id=product_id))
    # Always set up default price list for detail view
    mock.list_prices = AsyncMock(return_value=[])


@given('a billing product does not exist for SaaS "{saas_id}"')
def step_product_not_exists(context, saas_id):
    mock = context.mock_billing
    mock.get_product = AsyncMock(return_value=None)


@given('creating a billing product succeeds for SaaS "{saas_id}"')
def step_create_product_succeeds(context, saas_id):
    mock = context.mock_billing
    mock.create_product = AsyncMock(return_value=_make_product(id="prod-new"))


@given('creating a billing product fails for SaaS "{saas_id}"')
def step_create_product_fails(context, saas_id):
    mock = context.mock_billing
    mock.create_product = AsyncMock(return_value=None)


@given('updating a billing product succeeds for SaaS "{saas_id}"')
def step_update_product_succeeds(context, saas_id):
    mock = context.mock_billing
    mock.update_product = AsyncMock(return_value=_make_product())


@given('updating a billing product fails for SaaS "{saas_id}"')
def step_update_product_fails(context, saas_id):
    mock = context.mock_billing
    mock.update_product = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Price steps
# ---------------------------------------------------------------------------


@given('creating a billing price succeeds for SaaS "{saas_id}" product "{product_id}"')
def step_create_price_succeeds(context, saas_id, product_id):
    mock = context.mock_billing
    mock.create_price = AsyncMock(return_value=_make_price(id="price-new"))


@given('creating a billing price fails for SaaS "{saas_id}" product "{product_id}"')
def step_create_price_fails(context, saas_id, product_id):
    mock = context.mock_billing
    mock.create_price = AsyncMock(return_value=None)


@given(
    'toggling a billing price succeeds for SaaS "{saas_id}" product "{product_id}" price "{price_id}"'
)
def step_toggle_price_succeeds(context, saas_id, product_id, price_id):
    mock = context.mock_billing
    active_price = _make_price(id=price_id, is_active=True)
    mock.list_prices = AsyncMock(return_value=[active_price])
    toggled_price = _make_price(id=price_id, is_active=False)
    mock.update_price = AsyncMock(return_value=toggled_price)


@given(
    'toggling a billing price fails because price not found for SaaS "{saas_id}" product "{product_id}"'
)
def step_toggle_price_not_found(context, saas_id, product_id):
    mock = context.mock_billing
    mock.list_prices = AsyncMock(return_value=[])


# ---------------------------------------------------------------------------
# Customer steps
# ---------------------------------------------------------------------------


@given('the billing customers list returns data for SaaS "{saas_id}"')
def step_customers_list(context, saas_id):
    mock = context.mock_billing
    mock.list_customers = AsyncMock(return_value=[_make_customer()])


@given('a billing customer exists with id "{customer_id}" for SaaS "{saas_id}"')
def step_customer_exists(context, customer_id, saas_id):
    mock = context.mock_billing
    mock.get_customer = AsyncMock(return_value=_make_customer(id=customer_id))
    # Set up subscriptions for customer detail view
    mock.list_customer_subscriptions = AsyncMock(
        return_value=[_make_subscription(customer_id=customer_id)]
    )


@given('a billing customer does not exist for SaaS "{saas_id}"')
def step_customer_not_exists(context, saas_id):
    mock = context.mock_billing
    mock.get_customer = AsyncMock(return_value=None)


@given('the SaaS app "{saas_id}" accepts the return URL "{url}"')
def step_saas_accepts_return_url(context, saas_id, url):
    mock = context.mock_billing
    mock.get_saas_app = AsyncMock(
        return_value=_make_saas_app(id=saas_id, checkout_url_allowlist=[url])
    )


@given('the SaaS app "{saas_id}" has no checkout URL allow-list')
def step_saas_without_allowlist(context, saas_id):
    mock = context.mock_billing
    mock.get_saas_app = AsyncMock(return_value=_make_saas_app(id=saas_id))
    mock.get_customer_portal = AsyncMock(return_value=_make_portal())


@given('a billing customer portal URL exists for SaaS "{saas_id}" customer "{customer_id}"')
def step_customer_portal_exists(context, saas_id, customer_id):
    mock = context.mock_billing
    mock.get_customer_portal = AsyncMock(return_value=_make_portal())


@given('reactivating a billing subscription succeeds for SaaS "{saas_id}" subscription "{sub_id}"')
def step_reactivate_subscription_succeeds(context, saas_id, sub_id):
    mock = context.mock_billing
    mock.reactivate_subscription = AsyncMock(return_value=_make_subscription(id=sub_id))


@given('reactivating a billing subscription fails for SaaS "{saas_id}" subscription "{sub_id}"')
def step_reactivate_subscription_fails(context, saas_id, sub_id):
    mock = context.mock_billing
    mock.reactivate_subscription = AsyncMock(return_value=None)


@given('a billing customer portal fails for SaaS "{saas_id}" customer "{customer_id}"')
def step_customer_portal_fails(context, saas_id, customer_id):
    mock = context.mock_billing
    mock.get_customer_portal = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Subscription steps
# ---------------------------------------------------------------------------


@given('the billing subscriptions list returns data for SaaS "{saas_id}"')
def step_subscriptions_list(context, saas_id):
    mock = context.mock_billing
    mock.list_subscriptions = AsyncMock(return_value=[_make_subscription()])


@given('a billing subscription exists with id "{subscription_id}" for SaaS "{saas_id}"')
def step_subscription_exists(context, subscription_id, saas_id):
    mock = context.mock_billing
    sub = _make_subscription(id=subscription_id)
    mock.get_subscription = AsyncMock(return_value=sub)
    mock.get_customer = AsyncMock(return_value=_make_customer(id=sub.customer_id))


@given('a billing subscription does not exist for SaaS "{saas_id}"')
def step_subscription_not_exists(context, saas_id):
    mock = context.mock_billing
    mock.get_subscription = AsyncMock(return_value=None)


@given(
    'canceling a billing subscription succeeds for SaaS "{saas_id}" subscription "{subscription_id}"'
)
def step_cancel_subscription_succeeds(context, saas_id, subscription_id):
    mock = context.mock_billing
    mock.cancel_subscription = AsyncMock(
        return_value=_make_subscription(id=subscription_id, cancel_at_period_end=True)
    )


@given(
    'canceling a billing subscription fails for SaaS "{saas_id}" subscription "{subscription_id}"'
)
def step_cancel_subscription_fails(context, saas_id, subscription_id):
    mock = context.mock_billing
    mock.cancel_subscription = AsyncMock(return_value=None)


@given(
    'syncing a billing subscription succeeds for SaaS "{saas_id}" subscription "{subscription_id}"'
)
def step_sync_subscription_succeeds(context, saas_id, subscription_id):
    mock = context.mock_billing
    mock.sync_subscription = AsyncMock(return_value=_make_subscription(id=subscription_id))


@given('syncing a billing subscription fails for SaaS "{saas_id}" subscription "{subscription_id}"')
def step_sync_subscription_fails(context, saas_id, subscription_id):
    mock = context.mock_billing
    mock.sync_subscription = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Assertions on the calls made to the billing service
# ---------------------------------------------------------------------------


@then('the billing portal should have been requested with the return URL "{url}"')
def step_portal_return_url(context, url):
    context.mock_billing.get_customer_portal.assert_awaited_once()
    assert context.mock_billing.get_customer_portal.await_args.args[2] == url


@then("no billing portal should have been requested")
def step_no_portal(context):
    context.mock_billing.get_customer_portal.assert_not_awaited()


@then("the SaaS apps should have been listed with the inactive ones")
def step_saas_apps_with_inactive(context):
    context.mock_billing.list_saas_apps.assert_awaited_once_with(include_inactive=True)


@then("the SaaS app should have been updated as {state}")
def step_saas_app_updated_as(context, state):
    context.mock_billing.update_saas_app.assert_awaited_once()
    expected = {"active": True, "inactive": False}[state]
    assert context.mock_billing.update_saas_app.await_args.kwargs["is_active"] is expected


@then("the billing price should have been created with the service defaults")
def step_price_service_defaults(context):
    kwargs = context.mock_billing.create_price.await_args.kwargs
    assert kwargs["currency"] is None
    assert kwargs["recurring_interval"] is None
    assert kwargs["nickname"] is None


@then('the billing subscription "{sub_id}" should have been reactivated')
def step_subscription_reactivated(context, sub_id):
    context.mock_billing.reactivate_subscription.assert_awaited_once_with(
        saas_id="saas-1", subscription_id=sub_id
    )
