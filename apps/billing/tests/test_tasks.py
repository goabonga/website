# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Celery tasks."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from billing.config import settings
from billing.tasks import cleanup_old_usage_events, report_pending_usage
from billing.tasks.stripe_sync_tasks import (
    STRIPE_PRICE_ID_PATTERN,
    STRIPE_PRODUCT_ID_PATTERN,
    is_placeholder_stripe_id,
    sync_all_products_to_stripe,
)
from billing.tasks.usage_tasks import stripe_idempotency_key


def _make_mock_session():
    """Create a mock async session with context manager support."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _mock_session_factory(session):
    """Create a mock async session factory."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=mock_cm)
    return factory


def _mock_list_result(items):
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    r.scalars.return_value = scalars
    return r


def _mock_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


class TestStripeIdempotencyKey:
    """Keys are unique per SaaS app here but global in Stripe: they are namespaced."""

    def test_no_key_means_none(self):
        assert stripe_idempotency_key("saas-1", None) is None
        assert stripe_idempotency_key("saas-1", "") is None

    def test_same_key_in_two_saas_apps_gives_two_stripe_keys(self):
        assert stripe_idempotency_key("saas-1", "order-1") != stripe_idempotency_key(
            "saas-2", "order-1"
        )

    def test_key_is_stable_and_fits_stripe_limit(self):
        first = stripe_idempotency_key("saas-1", "k" * 255)
        assert first == stripe_idempotency_key("saas-1", "k" * 255)
        assert len(first) == 64


class TestIsPlaceholderStripeId:
    def test_placeholder_product(self):
        assert is_placeholder_stripe_id("fake_product_1", STRIPE_PRODUCT_ID_PATTERN) is True

    def test_real_product(self):
        assert is_placeholder_stripe_id("prod_AbCdEfGhIjKlMn", STRIPE_PRODUCT_ID_PATTERN) is False

    def test_placeholder_price(self):
        assert is_placeholder_stripe_id("fake_price_1", STRIPE_PRICE_ID_PATTERN) is True

    def test_real_price(self):
        assert is_placeholder_stripe_id("price_AbCdEfGhIjKlMn", STRIPE_PRICE_ID_PATTERN) is False


class TestReportPendingUsage:
    @patch("billing.tasks.usage_tasks.get_stripe_service")
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_no_pending_events(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()
        session.execute.return_value = _mock_list_result([])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = report_pending_usage(batch_size=100)
        assert result == {"processed": 0, "success": 0, "failed": 0}

    @patch("billing.tasks.usage_tasks.get_stripe_service")
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_process_events_success(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()

        event = MagicMock()
        event.id = "evt-1"
        event.subscription_id = "sub-1"
        event.quantity = 10
        event.timestamp = datetime(2024, 1, 1, tzinfo=UTC)
        event.idempotency_key = "key-1"

        sub = MagicMock()
        sub.stripe_subscription_item_id = "si_item1"

        mock_usage_record = MagicMock()
        mock_usage_record.id = "ur_123"

        mock_stripe = MagicMock()
        mock_stripe.report_usage.return_value = mock_usage_record
        mock_get_stripe.return_value = mock_stripe

        session.execute.side_effect = [
            _mock_list_result([event]),  # pending events
            _mock_result(sub),  # subscription lookup
        ]

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = report_pending_usage(batch_size=100)
        assert result["processed"] == 1
        assert result["success"] == 1

    @patch("billing.tasks.usage_tasks.get_stripe_service")
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_subscription_not_found(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()

        event = MagicMock()
        event.id = "evt-1"
        event.subscription_id = "sub-missing"

        session.execute.side_effect = [
            _mock_list_result([event]),
            _mock_result(None),  # No subscription
        ]

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = report_pending_usage(batch_size=100)
        assert result["failed"] == 1

    @patch("billing.tasks.usage_tasks.get_stripe_service")
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_no_subscription_item_id(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()

        event = MagicMock()
        event.id = "evt-1"
        event.subscription_id = "sub-1"

        sub = MagicMock()
        sub.stripe_subscription_item_id = None

        session.execute.side_effect = [
            _mock_list_result([event]),
            _mock_result(sub),
        ]

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = report_pending_usage(batch_size=100)
        assert result["failed"] == 1

    @patch("billing.tasks.usage_tasks.get_stripe_service")
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_stripe_error(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()

        event = MagicMock()
        event.id = "evt-1"
        event.subscription_id = "sub-1"
        event.quantity = 5
        event.timestamp = datetime(2024, 1, 1, tzinfo=UTC)
        event.idempotency_key = "key-1"

        sub = MagicMock()
        sub.stripe_subscription_item_id = "si_item1"

        mock_stripe = MagicMock()
        mock_stripe.report_usage.side_effect = Exception("Stripe error")
        mock_get_stripe.return_value = mock_stripe

        session.execute.side_effect = [
            _mock_list_result([event]),
            _mock_result(sub),
        ]

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = report_pending_usage(batch_size=100)
        assert result["failed"] == 1


class TestReportPendingUsageScoping:
    @patch("billing.tasks.usage_tasks.get_stripe_service")
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_stripe_receives_a_namespaced_idempotency_key(
        self, mock_factory_patch, mock_get_stripe
    ):
        session = _make_mock_session()
        event = MagicMock()
        event.id = "evt-1"
        event.saas_app_id = "saas-1"
        event.subscription_id = "sub-1"
        event.quantity = 3
        event.timestamp = datetime(2024, 1, 1, tzinfo=UTC)
        event.idempotency_key = "order-1"
        sub = MagicMock()
        sub.stripe_subscription_item_id = "si_item1"
        mock_stripe = MagicMock()
        mock_stripe.report_usage.return_value = {"id": "ur_1"}
        mock_get_stripe.return_value = mock_stripe
        session.execute.side_effect = [_mock_list_result([event]), _mock_result(sub)]
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        report_pending_usage(batch_size=10)

        sent = mock_stripe.report_usage.call_args.kwargs["idempotency_key"]
        assert sent == stripe_idempotency_key("saas-1", "order-1")
        assert sent != "order-1"

    @patch("billing.tasks.usage_tasks.get_stripe_service")
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_default_batch_size_comes_from_the_settings(
        self, mock_factory_patch, mock_get_stripe, monkeypatch
    ):
        monkeypatch.setattr(settings, "usage_report_batch_size", 7)
        session = _make_mock_session()
        session.execute.side_effect = [_mock_list_result([])]
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        report_pending_usage()

        query = session.execute.call_args_list[0][0][0].compile()
        assert 7 in query.params.values()


class TestCleanupOldUsageEvents:
    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_events_deleted(self, mock_factory_patch):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.rowcount = 42
        session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = cleanup_old_usage_events(days_old=90)
        assert result == {"deleted": 42}

    @patch("billing.tasks.usage_tasks.async_session_factory")
    def test_no_events_to_delete(self, mock_factory_patch):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = cleanup_old_usage_events(days_old=90)
        assert result == {"deleted": 0}


class TestSyncAllProductsToStripe:
    @patch("billing.tasks.stripe_sync_tasks.get_stripe_service")
    @patch("billing.tasks.stripe_sync_tasks.async_session_factory")
    def test_no_saas_apps(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()
        session.execute.return_value = _mock_list_result([])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = sync_all_products_to_stripe()
        assert result["products_synced"] == 0

    @patch("billing.tasks.stripe_sync_tasks.get_stripe_service")
    @patch("billing.tasks.stripe_sync_tasks.async_session_factory")
    def test_sync_products_and_prices(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()

        mock_stripe = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe.create_product.return_value = mock_stripe_product

        mock_stripe_price = MagicMock()
        mock_stripe_price.id = "price_RealStripeId12345"
        mock_stripe.create_price.return_value = mock_stripe_price
        mock_get_stripe.return_value = mock_stripe

        mock_price = MagicMock()
        mock_price.stripe_price_id = "placeholder_price"
        mock_price.unit_amount = 1000
        mock_price.currency = "usd"
        mock_price.billing_type = MagicMock(value="recurring")
        mock_price.recurring_interval = "month"
        mock_price.recurring_interval_count = 1
        mock_price.usage_type = MagicMock(value="licensed")
        mock_price.nickname = "Monthly"

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod"
        mock_product.name = "Test"
        mock_product.description = "Test desc"
        mock_product.extra_data = {
            "features": [
                {"label": "SSO", "disabled": False},
                {"label": "API access"},
            ]
        }
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.slug = "test"
        mock_saas.id = "saas-1"
        mock_saas.products = [mock_product]

        session.execute.return_value = _mock_list_result([mock_saas])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = sync_all_products_to_stripe()
        assert result["products_synced"] == 1
        assert result["prices_synced"] == 1

        # Verify features are included in the Stripe description
        call_kwargs = mock_stripe.create_product.call_args[1]
        assert "SSO" in call_kwargs["description"]
        assert "API access" in call_kwargs["description"]

    @patch("billing.tasks.stripe_sync_tasks.get_stripe_service")
    @patch("billing.tasks.stripe_sync_tasks.async_session_factory")
    def test_skip_real_ids(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()
        mock_get_stripe.return_value = MagicMock()

        mock_price = MagicMock()
        mock_price.stripe_price_id = "price_AbCdEfGhIjKlMn"  # Real ID

        mock_product = MagicMock()
        mock_product.stripe_product_id = "prod_AbCdEfGhIjKlMn"  # Real ID
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.slug = "test"
        mock_saas.products = [mock_product]

        session.execute.return_value = _mock_list_result([mock_saas])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = sync_all_products_to_stripe()
        assert result["products_skipped"] == 1

    @patch("billing.tasks.stripe_sync_tasks.get_stripe_service")
    @patch("billing.tasks.stripe_sync_tasks.async_session_factory")
    def test_skip_price_no_unit_amount(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()
        mock_stripe = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe.create_product.return_value = mock_stripe_product
        mock_get_stripe.return_value = mock_stripe

        mock_price = MagicMock()
        mock_price.stripe_price_id = "placeholder_price"
        mock_price.unit_amount = None
        mock_price.nickname = "Custom"

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod"
        mock_product.name = "Test"
        mock_product.description = "Test"
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.slug = "test"
        mock_saas.id = "saas-1"
        mock_saas.products = [mock_product]

        session.execute.return_value = _mock_list_result([mock_saas])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = sync_all_products_to_stripe()
        assert result["prices_skipped"] == 1
        assert result["products_synced"] == 1

    @patch("billing.tasks.stripe_sync_tasks.get_stripe_service")
    @patch("billing.tasks.stripe_sync_tasks.async_session_factory")
    def test_product_stripe_error(self, mock_factory_patch, mock_get_stripe):
        import stripe as stripe_mod

        session = _make_mock_session()
        mock_stripe = MagicMock()
        mock_stripe.create_product.side_effect = stripe_mod.error.StripeError("fail")
        mock_get_stripe.return_value = mock_stripe

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod"
        mock_product.name = "Test"
        mock_product.description = "Test"
        mock_product.extra_data = None
        mock_product.prices = []

        mock_saas = MagicMock()
        mock_saas.slug = "test"
        mock_saas.id = "saas-1"
        mock_saas.products = [mock_product]

        session.execute.return_value = _mock_list_result([mock_saas])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = sync_all_products_to_stripe()
        assert len(result["errors"]) == 1

    @patch("billing.tasks.stripe_sync_tasks.get_stripe_service")
    @patch("billing.tasks.stripe_sync_tasks.async_session_factory")
    def test_price_stripe_error(self, mock_factory_patch, mock_get_stripe):
        import stripe as stripe_mod

        session = _make_mock_session()
        mock_stripe = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe.create_product.return_value = mock_stripe_product
        mock_stripe.create_price.side_effect = stripe_mod.error.StripeError("price fail")
        mock_get_stripe.return_value = mock_stripe

        mock_price = MagicMock()
        mock_price.stripe_price_id = "placeholder_price"
        mock_price.unit_amount = 1000
        mock_price.currency = "usd"
        mock_price.billing_type = MagicMock(value="recurring")
        mock_price.recurring_interval = "month"
        mock_price.recurring_interval_count = 1
        mock_price.usage_type = MagicMock(value="licensed")
        mock_price.nickname = "Monthly"

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod"
        mock_product.name = "Test"
        mock_product.description = "Test"
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.slug = "test"
        mock_saas.id = "saas-1"
        mock_saas.products = [mock_product]

        session.execute.return_value = _mock_list_result([mock_saas])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = sync_all_products_to_stripe()
        assert result["products_synced"] == 1
        assert len(result["errors"]) == 1

    @patch("billing.tasks.stripe_sync_tasks.get_stripe_service")
    @patch("billing.tasks.stripe_sync_tasks.async_session_factory")
    def test_skip_price_with_real_id(self, mock_factory_patch, mock_get_stripe):
        session = _make_mock_session()
        mock_stripe = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe.create_product.return_value = mock_stripe_product
        mock_get_stripe.return_value = mock_stripe

        mock_price = MagicMock()
        mock_price.stripe_price_id = "price_AbCdEfGhIjKlMn"  # Real ID - skip
        mock_price.unit_amount = 1000

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod"
        mock_product.name = "Test"
        mock_product.description = "Test"
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.slug = "test"
        mock_saas.id = "saas-1"
        mock_saas.products = [mock_product]

        session.execute.return_value = _mock_list_result([mock_saas])

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory_patch.return_value = mock_cm

        result = sync_all_products_to_stripe()
        assert result["prices_skipped"] == 1
        assert result["products_synced"] == 1
