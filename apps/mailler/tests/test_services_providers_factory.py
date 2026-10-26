# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler/services/providers/factory.py."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clear_provider_cache():
    """Clear the global _providers cache before each test."""
    import mailler.services.providers.factory as factory_module

    factory_module._providers.clear()
    yield
    factory_module._providers.clear()


class TestGetProvider:
    """Tests for get_provider()."""

    def test_returns_brevo(self):
        """Returns a BrevoProvider instance when it is configured."""
        mock_provider = MagicMock()
        mock_provider.is_configured = True

        with (
            patch(
                "mailler.services.providers.factory.BrevoProvider",
                create=True,
            ),
            patch(
                "mailler.services.providers.brevo.BrevoProvider",
                return_value=mock_provider,
            ),
        ):
            from mailler.services.providers.factory import get_provider

            provider = get_provider("brevo")

        assert provider is mock_provider

    def test_unknown_provider_raises(self):
        """Raises ValueError for an unknown provider name."""
        from mailler.services.providers.factory import get_provider

        with pytest.raises(ValueError, match="Unknown email provider"):
            get_provider("unknown_provider")

    def test_not_configured_raises(self):
        """Raises ValueError when the provider is not properly configured."""
        mock_provider = MagicMock()
        mock_provider.is_configured = False

        with patch(
            "mailler.services.providers.brevo.BrevoProvider",
            return_value=mock_provider,
        ):
            from mailler.services.providers.factory import get_provider

            with pytest.raises(ValueError, match="not properly configured"):
                get_provider("brevo")

    def test_caches_provider(self):
        """A cached provider is returned on subsequent calls without re-creation."""
        mock_provider = MagicMock()
        mock_provider.is_configured = True

        with patch(
            "mailler.services.providers.brevo.BrevoProvider",
            return_value=mock_provider,
        ) as mock_cls:
            from mailler.services.providers.factory import get_provider

            first = get_provider("brevo")
            second = get_provider("brevo")

        assert first is second
        # The constructor should only have been called once
        mock_cls.assert_called_once()


class TestGetAvailableProviders:
    """Tests for get_available_providers()."""

    def test_returns_configured(self):
        """Returns only providers that are properly configured."""
        configured_provider = MagicMock()
        configured_provider.is_configured = True

        unconfigured_provider = MagicMock()
        unconfigured_provider.is_configured = False

        def mock_brevo():
            return configured_provider

        def mock_sendgrid():
            return unconfigured_provider

        def mock_ses():
            return configured_provider

        def mock_protonmail():
            return unconfigured_provider

        with (
            patch(
                "mailler.services.providers.brevo.BrevoProvider",
                side_effect=mock_brevo,
            ),
            patch(
                "mailler.services.providers.sendgrid.SendGridProvider",
                side_effect=mock_sendgrid,
            ),
            patch(
                "mailler.services.providers.ses.SESProvider",
                side_effect=mock_ses,
            ),
            patch(
                "mailler.services.providers.protonmail.ProtonmailProvider",
                side_effect=mock_protonmail,
            ),
        ):
            from mailler.services.providers.factory import get_available_providers

            available = get_available_providers()

        assert "brevo" in available
        assert "ses" in available
        assert "sendgrid" not in available
        assert "protonmail" not in available

    def test_returns_empty_when_none_configured(self):
        """Returns an empty list when no providers are configured."""
        unconfigured = MagicMock()
        unconfigured.is_configured = False

        with (
            patch(
                "mailler.services.providers.brevo.BrevoProvider",
                return_value=unconfigured,
            ),
            patch(
                "mailler.services.providers.sendgrid.SendGridProvider",
                return_value=unconfigured,
            ),
            patch(
                "mailler.services.providers.ses.SESProvider",
                return_value=unconfigured,
            ),
            patch(
                "mailler.services.providers.protonmail.ProtonmailProvider",
                return_value=unconfigured,
            ),
        ):
            from mailler.services.providers.factory import get_available_providers

            available = get_available_providers()

        assert available == []

    def test_cached_provider_becomes_unconfigured(self):
        """Cover branch line 81->78: cached provider returns is_configured=False.

        When a provider is already cached (get_provider returns it without
        raising), but its is_configured property returns False, the provider
        should be skipped and the loop continues.
        """
        import mailler.services.providers.factory as factory_module

        # Pre-populate the cache with a provider that is NOT configured.
        # This bypasses the get_provider validation check and simulates a
        # provider whose configuration was invalidated after initial caching.
        stale_provider = MagicMock()
        stale_provider.is_configured = False
        factory_module._providers["brevo"] = stale_provider

        # For the remaining providers, make get_provider raise ValueError
        unconfigured = MagicMock()
        unconfigured.is_configured = False

        with (
            patch(
                "mailler.services.providers.sendgrid.SendGridProvider",
                return_value=unconfigured,
            ),
            patch(
                "mailler.services.providers.ses.SESProvider",
                return_value=unconfigured,
            ),
            patch(
                "mailler.services.providers.protonmail.ProtonmailProvider",
                return_value=unconfigured,
            ),
        ):
            from mailler.services.providers.factory import get_available_providers

            available = get_available_providers()

        # brevo was cached but unconfigured, so it should NOT be in the list
        assert "brevo" not in available
        assert available == []
