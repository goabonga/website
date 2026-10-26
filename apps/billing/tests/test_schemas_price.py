# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/schemas/price.py."""

import pytest
from billing.config import settings
from billing.models.price import BillingType, UsageType
from billing.schemas.price import PriceCreate
from pydantic import ValidationError


class TestPriceCreateValidation:
    """Tests for PriceCreate schema validation."""

    def test_valid_recurring_price(self):
        """Should accept a valid recurring price."""
        price = PriceCreate(
            nickname="Monthly Plan",
            currency="usd",
            unit_amount=1000,
            billing_type=BillingType.RECURRING,
            recurring_interval="month",
            recurring_interval_count=1,
            usage_type=UsageType.LICENSED,
        )
        assert price.unit_amount == 1000
        assert price.recurring_interval == "month"

    def test_valid_recurring_intervals(self):
        """Should accept all valid recurring interval values."""
        for interval in ["day", "week", "month", "year"]:
            price = PriceCreate(
                unit_amount=100,
                recurring_interval=interval,
            )
            assert price.recurring_interval == interval

    def test_invalid_recurring_interval(self):
        """Should reject invalid recurring interval values."""
        with pytest.raises(ValidationError) as exc_info:
            PriceCreate(
                unit_amount=100,
                recurring_interval="biweekly",
            )
        assert "recurring_interval" in str(exc_info.value)

    def test_unit_amount_must_be_non_negative(self):
        """Should reject negative unit_amount."""
        with pytest.raises(ValidationError) as exc_info:
            PriceCreate(unit_amount=-1)
        assert "unit_amount" in str(exc_info.value)

    def test_unit_amount_zero_is_valid(self):
        """Should accept unit_amount of zero (free tier)."""
        price = PriceCreate(unit_amount=0)
        assert price.unit_amount == 0

    def test_unit_amount_none_is_valid(self):
        """Should accept None unit_amount (for metered pricing)."""
        price = PriceCreate(unit_amount=None)
        assert price.unit_amount is None

    def test_default_values(self):
        """Should have sensible defaults."""
        price = PriceCreate()
        assert price.currency == "usd"
        assert price.billing_type == BillingType.RECURRING
        assert price.recurring_interval_count == 1
        assert price.usage_type == UsageType.LICENSED
        assert price.nickname is None
        assert price.unit_amount is None
        assert price.recurring_interval is None

    def test_currency_length_validation(self):
        """Currency must be exactly 3 characters."""
        with pytest.raises(ValidationError):
            PriceCreate(currency="us")

        with pytest.raises(ValidationError):
            PriceCreate(currency="usdx")

    def test_recurring_interval_count_minimum(self):
        """recurring_interval_count must be >= 1."""
        with pytest.raises(ValidationError):
            PriceCreate(recurring_interval_count=0)

    def test_recurring_interval_count_maximum(self):
        """recurring_interval_count must be <= 365."""
        with pytest.raises(ValidationError):
            PriceCreate(recurring_interval_count=366)

    def test_valid_one_time_price(self):
        """Should accept a one-time price without recurring interval."""
        price = PriceCreate(
            nickname="One-time Setup",
            unit_amount=5000,
            billing_type=BillingType.ONE_TIME,
        )
        assert price.billing_type == BillingType.ONE_TIME
        assert price.recurring_interval is None


class TestPriceCurrencyDefault:
    """The currency of a price defaults to the configured one."""

    def test_default_currency_comes_from_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "default_currency", "eur")

        assert PriceCreate(unit_amount=100).currency == "eur"

    def test_explicit_currency_wins(self, monkeypatch):
        monkeypatch.setattr(settings, "default_currency", "eur")

        assert PriceCreate(unit_amount=100, currency="chf").currency == "chf"
