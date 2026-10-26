# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/schemas/saas_app.py."""

import pytest
from billing.schemas.saas_app import SaasAppCreate, SaasAppUpdate, validate_url_allowlist
from pydantic import ValidationError


class TestSaasAppCreateSlugValidation:
    """Tests for SaasAppCreate slug validation."""

    def test_valid_slug_lowercase(self):
        """Should accept lowercase alphabetic slugs."""
        app = SaasAppCreate(name="Test", slug="myapp")
        assert app.slug == "myapp"

    def test_valid_slug_with_numbers(self):
        """Should accept slugs with numbers."""
        app = SaasAppCreate(name="Test", slug="app123")
        assert app.slug == "app123"

    def test_valid_slug_with_hyphens(self):
        """Should accept slugs with hyphens."""
        app = SaasAppCreate(name="Test", slug="my-cool-app")
        assert app.slug == "my-cool-app"

    def test_valid_slug_single_char(self):
        """Should accept single character slugs."""
        app = SaasAppCreate(name="Test", slug="a")
        assert app.slug == "a"

    def test_invalid_slug_uppercase(self):
        """Should reject slugs with uppercase letters."""
        with pytest.raises(ValidationError) as exc_info:
            SaasAppCreate(name="Test", slug="MyApp")
        assert "slug" in str(exc_info.value)

    def test_invalid_slug_spaces(self):
        """Should reject slugs with spaces."""
        with pytest.raises(ValidationError):
            SaasAppCreate(name="Test", slug="my app")

    def test_invalid_slug_underscores(self):
        """Should reject slugs with underscores."""
        with pytest.raises(ValidationError):
            SaasAppCreate(name="Test", slug="my_app")

    def test_invalid_slug_special_chars(self):
        """Should reject slugs with special characters."""
        with pytest.raises(ValidationError):
            SaasAppCreate(name="Test", slug="my@app!")

    def test_invalid_slug_empty(self):
        """Should reject empty slug (min_length=1)."""
        with pytest.raises(ValidationError):
            SaasAppCreate(name="Test", slug="")

    def test_name_required(self):
        """Should require the name field."""
        with pytest.raises(ValidationError):
            SaasAppCreate(slug="test-app")

    def test_optional_fields(self):
        """Optional fields should default to None."""
        app = SaasAppCreate(name="Test", slug="test")
        assert app.description is None
        assert app.webhook_url is None
        assert app.webhook_secret is None
        assert app.branding is None
        assert app.checkout_url_allowlist is None


class TestCheckoutUrlAllowlist:
    """Tests for the checkout URL allow-list of a SaaS application."""

    def test_origins_and_paths_are_accepted_and_normalized(self):
        app = SaasAppCreate(
            name="Test",
            slug="test",
            checkout_url_allowlist=[
                "https://app.example.test/",
                " http://localhost:3000/billing/ ",
            ],
        )

        assert app.checkout_url_allowlist == [
            "https://app.example.test",
            "http://localhost:3000/billing",
        ]

    @pytest.mark.parametrize(
        "entry",
        [
            "app.example.test",
            "ftp://app.example.test",
            "https://",
            "https://user:pass@app.example.test",
            "https://app.example.test/?a=1",
            "https://app.example.test/#frag",
            "",
        ],
    )
    def test_invalid_entries_are_rejected(self, entry):
        with pytest.raises(ValidationError):
            SaasAppUpdate(checkout_url_allowlist=[entry])

    def test_none_clears_the_allowlist(self):
        assert validate_url_allowlist(None) is None
        assert SaasAppUpdate(checkout_url_allowlist=None).model_dump(exclude_unset=True) == {
            "checkout_url_allowlist": None
        }

    def test_empty_list_is_accepted(self):
        assert (
            SaasAppCreate(name="T", slug="t", checkout_url_allowlist=[]).checkout_url_allowlist
            == []
        )
