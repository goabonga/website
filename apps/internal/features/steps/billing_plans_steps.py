# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the slug and the free-form limits of billing products."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from behave import given, then


def _product(slug, extra_data):
    """Create a mock product with a slug and metadata."""
    product = MagicMock()
    product.id = "prod-1"
    product.name = "Test Product"
    product.description = "A test product"
    product.slug = slug
    product.stripe_product_id = "stripe_prod_123"
    product.is_active = True
    product.created_at = datetime(2024, 1, 1)
    product.extra_data = extra_data
    return product


def _saas_app(saas_id="saas-1"):
    saas_app = MagicMock()
    saas_app.id = saas_id
    saas_app.name = "Test App"
    return saas_app


@given('the SaaS app "{saas_id}" has the product "{slug}" with the metadata \'{metadata}\'')
def step_product_with_metadata(context, saas_id, slug, metadata):
    mock = context.mock_billing
    product = _product(slug, json.loads(metadata))
    mock.get_saas_app = AsyncMock(return_value=_saas_app(saas_id))
    mock.get_product = AsyncMock(return_value=product)
    mock.list_products = AsyncMock(return_value=[product])
    mock.list_prices = AsyncMock(return_value=[])
    mock.update_product = AsyncMock(return_value=product)
    mock.create_product = AsyncMock(return_value=product)


@then('the product should have been created with the slug "{slug}"')
def step_created_with_slug(context, slug):
    kwargs = context.mock_billing.create_product.await_args.kwargs
    assert kwargs["slug"] == slug, kwargs
    assert "slug" not in kwargs["metadata"], kwargs


@then("the product should have been created without a slug")
def step_created_without_slug(context):
    kwargs = context.mock_billing.create_product.await_args.kwargs
    assert kwargs["slug"] is None, kwargs


@then("no product should have been created")
def step_nothing_created(context):
    context.mock_billing.create_product.assert_not_awaited()


@then("no product should have been updated")
def step_nothing_updated(context):
    context.mock_billing.update_product.assert_not_awaited()


@then('the product should have been updated with the slug "{slug}"')
def step_updated_with_slug(context, slug):
    assert context.mock_billing.update_product.await_args.kwargs["slug"] == slug


@then("the product metadata should have been updated as '{expected}'")
def step_updated_metadata(context, expected):
    metadata = context.mock_billing.update_product.await_args.kwargs["metadata"]
    wanted = json.loads(expected)
    actual = {key: metadata.get(key) for key in wanted}
    assert actual == wanted, metadata
