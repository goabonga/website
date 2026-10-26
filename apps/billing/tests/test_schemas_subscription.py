# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/schemas/subscription.py."""

from datetime import UTC

import pytest
from billing.config import settings
from billing.schemas.subscription import (
    ProrationLineItem,
    SubscriptionCreate,
    SubscriptionUpgradePreview,
)
from pydantic import ValidationError


class TestProrationLineItemDisplayAmount:
    """Tests for ProrationLineItem.display_amount property."""

    def test_positive_whole_dollars(self):
        """Should display whole dollar amounts without cents."""
        item = ProrationLineItem(description="Upgrade", amount=1000, currency="usd")
        assert item.display_amount == "10 USD"

    def test_positive_with_cents(self):
        """Should display amounts with cents formatted to 2 decimal places."""
        item = ProrationLineItem(description="Upgrade", amount=1050, currency="usd")
        assert item.display_amount == "10.50 USD"

    def test_negative_amount_credit(self):
        """Should display negative amounts with a minus sign."""
        item = ProrationLineItem(description="Credit", amount=-500, currency="usd")
        assert item.display_amount == "-5 USD"

    def test_negative_with_cents(self):
        """Should display negative amounts with cents."""
        item = ProrationLineItem(description="Credit", amount=-1525, currency="usd")
        assert item.display_amount == "-15.25 USD"

    def test_zero_amount(self):
        """Should display zero without decimals."""
        item = ProrationLineItem(description="No change", amount=0, currency="usd")
        assert item.display_amount == "0 USD"

    def test_small_amount_cents_only(self):
        """Should display amounts less than a dollar correctly."""
        item = ProrationLineItem(description="Small charge", amount=50, currency="usd")
        assert item.display_amount == "0.50 USD"

    def test_one_cent(self):
        """Should display one cent correctly."""
        item = ProrationLineItem(description="Tiny", amount=1, currency="usd")
        assert item.display_amount == "0.01 USD"

    def test_large_amount(self):
        """Should handle large amounts correctly."""
        item = ProrationLineItem(description="Big upgrade", amount=999900, currency="usd")
        assert item.display_amount == "9999 USD"


class TestSubscriptionUpgradePreviewDisplayTotal:
    """Tests for SubscriptionUpgradePreview.display_total property."""

    def _make_preview(self, total: int) -> SubscriptionUpgradePreview:
        """Create a minimal SubscriptionUpgradePreview with the given total."""
        from datetime import datetime

        return SubscriptionUpgradePreview(
            current_plan_name="Basic",
            new_plan_name="Pro",
            current_price_amount=1000,
            new_price_amount=2000,
            proration_date=datetime.now(UTC),
            period_end=datetime.now(UTC),
            line_items=[],
            subtotal=total,
            total=total,
            credit_applied=0,
            currency="usd",
        )

    def test_positive_whole_dollars(self):
        """Should display whole dollar totals without cents."""
        preview = self._make_preview(2000)
        assert preview.display_total == "20 USD"

    def test_positive_with_cents(self):
        """Should display totals with cents."""
        preview = self._make_preview(2550)
        assert preview.display_total == "25.50 USD"

    def test_negative_total(self):
        """Should display negative totals (credit) with minus sign."""
        preview = self._make_preview(-1000)
        assert preview.display_total == "-10 USD"

    def test_negative_with_cents(self):
        """Should display negative totals with cents."""
        preview = self._make_preview(-750)
        assert preview.display_total == "-7.50 USD"

    def test_zero_total(self):
        """Should display a zero total without decimals."""
        preview = self._make_preview(0)
        assert preview.display_total == "0 USD"


class TestCurrency:
    """The currency is part of the display and defaults to the configured one."""

    def test_amount_is_followed_by_its_currency_code(self):
        item = ProrationLineItem(description="Upgrade", amount=1050, currency="eur")

        assert item.display_amount == "10.50 EUR"

    def test_currency_defaults_to_the_configured_one(self, monkeypatch):
        monkeypatch.setattr(settings, "default_currency", "chf")

        assert ProrationLineItem(description="Upgrade", amount=100).currency == "chf"


class TestSubscriptionCreateTrial:
    """The trial period is bounded by the settings."""

    def test_trial_up_to_the_maximum_is_accepted(self):
        days = settings.max_trial_period_days

        assert SubscriptionCreate(price_id="p", trial_period_days=days).trial_period_days == days

    def test_trial_above_the_maximum_is_rejected(self):
        with pytest.raises(ValidationError):
            SubscriptionCreate(price_id="p", trial_period_days=settings.max_trial_period_days + 1)

    def test_negative_trial_is_rejected(self):
        with pytest.raises(ValidationError):
            SubscriptionCreate(price_id="p", trial_period_days=-1)
