# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/models/."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from billing.config import settings
from billing.models.customer import Customer
from billing.models.price import BillingPrice, BillingType, UsageType
from billing.models.product import BillingProduct
from billing.models.saas_app import SaasApp
from billing.models.subscription import SubscriptionStatus
from billing.models.usage_event import UsageEvent, UsageEventStatus
from sqlalchemy import UniqueConstraint


def _unique_columns(model) -> set[tuple[str, ...]]:
    """Return the column names of every unique constraint of a model's table."""
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


class TestSaasScoping:
    """Plan slugs and idempotency keys are scoped to a SaaS application."""

    def test_product_slug_is_unique_per_saas_app(self):
        """Two SaaS applications may reuse a slug, one may not use it twice."""
        assert ("saas_app_id", "slug") in _unique_columns(BillingProduct)
        assert BillingProduct.__table__.c.slug.nullable is False

    def test_idempotency_key_is_unique_per_saas_app(self):
        """The idempotency key is not globally unique any more."""
        assert ("saas_app_id", "idempotency_key") in _unique_columns(UsageEvent)
        assert UsageEvent.__table__.c.idempotency_key.unique is not True
        assert UsageEvent.__table__.c.saas_app_id.nullable is False

    def test_saas_app_has_checkout_url_allowlist(self):
        """Each SaaS application can list its accepted checkout redirect targets."""
        assert SaasApp.__table__.c.checkout_url_allowlist.nullable is True


class TestPriceCurrencyDefault:
    """The default currency comes from the settings."""

    def test_default_currency_is_read_from_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "default_currency", "eur")
        default = BillingPrice.__table__.c.currency.default
        assert default.arg(None) == "eur"


class TestCustomerIsDeleted:
    """Tests for Customer.is_deleted property."""

    def test_is_deleted_when_deleted_at_is_set(self):
        """Should return True when deleted_at has a datetime value."""
        mock = MagicMock()
        mock.deleted_at = datetime.now(UTC)
        assert Customer.is_deleted.fget(mock) is True

    def test_is_not_deleted_when_deleted_at_is_none(self):
        """Should return False when deleted_at is None."""
        mock = MagicMock()
        mock.deleted_at = None
        assert Customer.is_deleted.fget(mock) is False


class TestSubscriptionStatus:
    """Tests for SubscriptionStatus enum."""

    def test_active_value(self):
        assert SubscriptionStatus.ACTIVE == "active"
        assert SubscriptionStatus.ACTIVE.value == "active"

    def test_past_due_value(self):
        assert SubscriptionStatus.PAST_DUE == "past_due"
        assert SubscriptionStatus.PAST_DUE.value == "past_due"

    def test_unpaid_value(self):
        assert SubscriptionStatus.UNPAID == "unpaid"
        assert SubscriptionStatus.UNPAID.value == "unpaid"

    def test_canceled_value(self):
        assert SubscriptionStatus.CANCELED == "canceled"
        assert SubscriptionStatus.CANCELED.value == "canceled"

    def test_incomplete_value(self):
        assert SubscriptionStatus.INCOMPLETE == "incomplete"
        assert SubscriptionStatus.INCOMPLETE.value == "incomplete"

    def test_incomplete_expired_value(self):
        assert SubscriptionStatus.INCOMPLETE_EXPIRED == "incomplete_expired"
        assert SubscriptionStatus.INCOMPLETE_EXPIRED.value == "incomplete_expired"

    def test_trialing_value(self):
        assert SubscriptionStatus.TRIALING == "trialing"
        assert SubscriptionStatus.TRIALING.value == "trialing"

    def test_paused_value(self):
        assert SubscriptionStatus.PAUSED == "paused"
        assert SubscriptionStatus.PAUSED.value == "paused"

    def test_all_values_count(self):
        """SubscriptionStatus should have exactly 8 members."""
        assert len(SubscriptionStatus) == 8

    def test_is_str_enum(self):
        """SubscriptionStatus values should be usable as strings."""
        assert isinstance(SubscriptionStatus.ACTIVE, str)
        assert SubscriptionStatus.ACTIVE.value == "active"


class TestUsageEventStatus:
    """Tests for UsageEventStatus enum."""

    def test_pending_value(self):
        assert UsageEventStatus.PENDING == "pending"
        assert UsageEventStatus.PENDING.value == "pending"

    def test_reported_value(self):
        assert UsageEventStatus.REPORTED == "reported"
        assert UsageEventStatus.REPORTED.value == "reported"

    def test_failed_value(self):
        assert UsageEventStatus.FAILED == "failed"
        assert UsageEventStatus.FAILED.value == "failed"

    def test_all_values_count(self):
        """UsageEventStatus should have exactly 3 members."""
        assert len(UsageEventStatus) == 3

    def test_is_str_enum(self):
        """UsageEventStatus values should be usable as strings."""
        assert isinstance(UsageEventStatus.PENDING, str)


class TestBillingType:
    """Tests for BillingType enum."""

    def test_one_time_value(self):
        assert BillingType.ONE_TIME == "one_time"
        assert BillingType.ONE_TIME.value == "one_time"

    def test_recurring_value(self):
        assert BillingType.RECURRING == "recurring"
        assert BillingType.RECURRING.value == "recurring"

    def test_all_values_count(self):
        """BillingType should have exactly 2 members."""
        assert len(BillingType) == 2

    def test_is_str_enum(self):
        """BillingType values should be usable as strings."""
        assert isinstance(BillingType.RECURRING, str)


class TestUsageType:
    """Tests for UsageType enum."""

    def test_licensed_value(self):
        assert UsageType.LICENSED == "licensed"
        assert UsageType.LICENSED.value == "licensed"

    def test_metered_value(self):
        assert UsageType.METERED == "metered"
        assert UsageType.METERED.value == "metered"

    def test_all_values_count(self):
        """UsageType should have exactly 2 members."""
        assert len(UsageType) == 2

    def test_is_str_enum(self):
        """UsageType values should be usable as strings."""
        assert isinstance(UsageType.METERED, str)
