# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/templating.py and the deployment values of the public pages."""

from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from knowledge import templating
from knowledge.config import Settings
from knowledge.templating import create_templates, format_limit, limit_label, site


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


class TestLimitHelpers:
    @pytest.mark.parametrize(
        ("name", "label"),
        [
            ("max_total_documents", "Total documents"),
            ("max_storage_bytes", "Storage"),
            ("seats", "Seats"),
            ("max_", "max_"),
        ],
    )
    def test_label(self, name, label):
        assert limit_label(name) == label

    @pytest.mark.parametrize(
        ("name", "value", "text"),
        [
            ("max_collections", -1, "Unlimited"),
            ("max_collections", None, "-"),
            ("max_collections", 100000, "100,000"),
            ("max_storage_bytes", 50 * 1024 * 1024, "50 MB"),
            ("max_storage_bytes", 1536, "1.5 KB"),
            ("max_storage_bytes", 5 * 1024**3, "5 GB"),
            ("max_storage_bytes", 2 * 1024**5, "2048 TB"),
        ],
    )
    def test_value(self, name, value, text):
        assert format_limit(name, value) == text


class TestSite:
    def test_nothing_is_built_in(self):
        with patch.object(templating, "get_settings", return_value=_settings()):
            assert set(site().values()) == {""}

    def test_values_come_from_the_settings(self):
        settings = _settings(
            operator_name="Acme",
            sales_email="sales@acme.test",
            app_base_url="https://kb.acme.test/",
        )
        with patch.object(templating, "get_settings", return_value=settings):
            info = site()
        assert info["operator_name"] == "Acme"
        assert info["sales_email"] == "sales@acme.test"
        assert info["base_url"] == "https://kb.acme.test"


def _plan(name, limits, custom=False):
    price = NS(is_custom=custom, unit_amount=None if custom else 0, display_amount="0", id="p")
    return NS(
        name=name,
        slug=name.lower(),
        description="",
        features=[],
        limits=limits,
        prices=[],
        is_recommended=False,
        monthly_price=price,
        yearly_price=None,
        is_free=False,
        yearly_savings_percent=0,
        yearly_monthly_equivalent="0",
    )


def _render(plans, **settings):
    with patch.object(templating, "get_settings", return_value=_settings(**settings)):
        return create_templates().get_template("pages/pricing.html").render(plans=plans)


class TestPricingPage:
    def test_comparison_lists_the_limits_of_the_plans(self):
        html = _render(
            [
                _plan("Small", {"max_collections": 3, "max_storage_bytes": 52428800}),
                _plan("Big", {"max_collections": -1, "max_seats": 9}),
            ]
        )
        assert "Feature Comparison" in html
        assert "<th>Small</th>" in html and "<th>Big</th>" in html
        assert "Collections" in html and "Seats" in html
        assert "50 MB" in html and "Unlimited" in html

    def test_no_plans_no_invented_prices(self):
        html = _render([])
        assert "not available right now" in html
        assert "Feature Comparison" not in html
        assert "$19" not in html and "$79" not in html

    def test_contact_sales_only_with_a_configured_address(self):
        plans = [_plan("Custom", {"max_collections": 1}, custom=True)]
        assert "Contact Sales" not in _render(plans)
        html = _render(plans, sales_email="sales@acme.test")
        assert "mailto:sales@acme.test" in html

    @pytest.mark.parametrize("page", ["legal", "terms", "privacy"])
    def test_legal_pages_carry_no_built_in_address(self, page):
        with patch.object(templating, "get_settings", return_value=_settings()):
            html = create_templates().get_template(f"pages/{page}.html").render()
        assert "goabonga" not in html and "mailto:" not in html

    def test_legal_pages_use_the_configured_addresses(self):
        settings = _settings(legal_email="legal@acme.test", operator_name="Acme")
        with patch.object(templating, "get_settings", return_value=settings):
            html = create_templates().get_template("pages/legal.html").render()
        assert "mailto:legal@acme.test" in html and "provided by Acme" in html


PUBLIC_PAGES = ["home", "pricing", "legal", "terms", "privacy", "mcp_downloads"]


def _render_public(page, cookies=None, **context):
    with patch.object(templating, "get_settings", return_value=_settings()):
        return (
            create_templates()
            .get_template(f"pages/{page}.html")
            .render(
                request=NS(cookies=cookies or {}),
                plans=[],
                releases=[],
                latest_release=None,
                **context,
            )
        )


class TestPublicHeader:
    @pytest.mark.parametrize("page", PUBLIC_PAGES)
    def test_visitors_are_offered_to_sign_in(self, page):
        html = _render_public(page)
        assert 'href="/auth/signin"' in html
        assert 'href="/dashboard"' not in html

    @pytest.mark.parametrize("page", PUBLIC_PAGES)
    def test_signed_in_users_are_offered_their_dashboard(self, page):
        html = _render_public(page, {"access_token": "token"})
        assert 'href="/dashboard"' in html
        assert 'href="/auth/signin"' not in html

    @pytest.mark.parametrize("page", PUBLIC_PAGES)
    @pytest.mark.parametrize("docs_enabled", [False, True])
    def test_the_documentation_is_linked_only_when_it_is_served(self, page, docs_enabled):
        html = _render_public(page, docs_enabled=docs_enabled)
        assert ('href="/docs"' in html) is docs_enabled
