# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing.services.redirects."""

from unittest.mock import MagicMock

import pytest
from billing.config import settings
from billing.services.redirects import (
    RedirectNotAllowed,
    ensure_allowed_redirect,
    matches_allowlist,
)


def _saas(allowlist):
    saas = MagicMock()
    saas.slug = "test-app"
    saas.checkout_url_allowlist = allowlist
    return saas


class TestMatchesAllowlist:
    """A URL must be covered by one prefix of the allow-list."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://app.example.test",
            "https://app.example.test/",
            "https://app.example.test/any/path?x=1#frag",
            "https://APP.example.test/ok",
            "https://app.example.test:443/ok",
        ],
    )
    def test_origin_prefix_covers_the_whole_origin(self, url):
        assert matches_allowlist(url, ["https://app.example.test"]) is True

    def test_path_prefix_is_segment_aware(self):
        allowlist = ["https://app.example.test/billing"]

        assert matches_allowlist("https://app.example.test/billing", allowlist) is True
        assert matches_allowlist("https://app.example.test/billing/done", allowlist) is True
        assert matches_allowlist("https://app.example.test/billing-other", allowlist) is False
        assert matches_allowlist("https://app.example.test/", allowlist) is False

    @pytest.mark.parametrize(
        "url",
        [
            "http://app.example.test/ok",
            "https://app.example.test.evil.test/ok",
            "https://evil.test/https://app.example.test",
            "https://app.example.test:8443/ok",
            "https://user:pass@app.example.test/ok",
            "javascript:alert(1)",
            "ftp://app.example.test",
            "//app.example.test/ok",
            "not a url",
            "",
        ],
    )
    def test_other_targets_are_refused(self, url):
        assert matches_allowlist(url, ["https://app.example.test"]) is False

    def test_any_entry_may_match(self):
        allowlist = ["https://a.example.test", "http://localhost:3000"]

        assert matches_allowlist("http://localhost:3000/done", allowlist) is True
        assert matches_allowlist("http://localhost:3001/done", allowlist) is False

    def test_empty_allowlist_matches_nothing(self):
        assert matches_allowlist("https://app.example.test", []) is False


class TestEnsureAllowedRedirect:
    """The allow-list of the SaaS application decides, the setting covers the empty case."""

    def test_listed_url_is_accepted(self):
        ensure_allowed_redirect(
            _saas(["https://app.example.test"]), "https://app.example.test/ok", "success_url"
        )

    def test_unlisted_url_is_refused(self):
        with pytest.raises(RedirectNotAllowed, match="success_url"):
            ensure_allowed_redirect(
                _saas(["https://app.example.test"]), "https://evil.test/ok", "success_url"
            )

    @pytest.mark.parametrize("allowlist", [None, []])
    def test_missing_allowlist_is_refused_by_default(self, allowlist):
        with pytest.raises(RedirectNotAllowed, match="test-app"):
            ensure_allowed_redirect(_saas(allowlist), "https://app.example.test/ok", "cancel_url")

    @pytest.mark.parametrize("allowlist", [None, []])
    def test_missing_allowlist_can_be_tolerated(self, allowlist, monkeypatch):
        monkeypatch.setattr(settings, "redirect_allowlist_required", False)

        ensure_allowed_redirect(_saas(allowlist), "https://anywhere.example.test", "cancel_url")

    def test_a_defined_allowlist_is_enforced_even_when_not_required(self, monkeypatch):
        monkeypatch.setattr(settings, "redirect_allowlist_required", False)

        with pytest.raises(RedirectNotAllowed):
            ensure_allowed_redirect(
                _saas(["https://app.example.test"]), "https://evil.test", "cancel_url"
            )
