# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the billing administration."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from behave import given, then
from internal.config import settings


@given("the billing lists show {count:d} rows per page")
def step_billing_page_size(context, count):
    patcher = patch.object(settings, "billing_page_size", count)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('the billing customers list returns {count:d} customers for SaaS "{saas_id}"')
def step_many_customers(context, count, saas_id):
    customers = []
    for index in range(count):
        customer = MagicMock()
        customer.id = f"cust-{index}"
        customer.email = f"customer{index}@example.com"
        customer.name = f"Customer {index}"
        customer.stripe_customer_id = f"stripe_cus_{index}"
        customer.external_id = f"ext-{index}"
        customer.created_at = datetime(2024, 1, 1)
        customers.append(customer)
    context.mock_billing.list_customers = AsyncMock(return_value=customers)


@then('the billing service should have been asked to create the SaaS app "{name}"')
def step_created_saas_app(context, name):
    kwargs = context.mock_billing.create_saas_app.await_args.kwargs
    assert kwargs["name"] == name, kwargs


@then('the billing service should have been asked to create the product "{name}"')
def step_created_product(context, name):
    kwargs = context.mock_billing.create_product.await_args.kwargs
    assert kwargs["name"] == name, kwargs


@then('the created product should list the feature "{label}"')
def step_created_product_feature(context, label):
    metadata = context.mock_billing.create_product.await_args.kwargs["metadata"]
    assert label in [feature["label"] for feature in metadata["features"]], metadata


@then("the billing service should not have been asked to create a SaaS app")
def step_no_saas_app_created(context):
    context.mock_billing.create_saas_app.assert_not_awaited()


@then("the product should have been created with the limits '{limits}'")
def step_created_with_limits(context, limits):
    import json

    metadata = context.mock_billing.create_product.await_args.kwargs["metadata"]
    assert metadata["limits"] == json.loads(limits), metadata
