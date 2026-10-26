# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email provider factory."""

from mailler.logging import get_logger
from mailler.services.providers.base import EmailProvider

logger = get_logger(__name__)

# Provider adapters shipped with the service (name -> class path)
PROVIDER_CLASSES = {
    "brevo": "mailler.services.providers.brevo.BrevoProvider",
    "sendgrid": "mailler.services.providers.sendgrid.SendGridProvider",
    "ses": "mailler.services.providers.ses.SESProvider",
    "protonmail": "mailler.services.providers.protonmail.ProtonmailProvider",
}

# Provider cache
_providers: dict[str, EmailProvider] = {}


def known_providers() -> list[str]:
    """Get the names of the provider adapters, configured or not."""
    return list(PROVIDER_CLASSES)


def get_provider(provider_name: str) -> EmailProvider:
    """Get an email provider by name.

    Args:
        provider_name: Provider name (brevo, sendgrid, ses, protonmail)

    Returns:
        EmailProvider instance

    Raises:
        ValueError: If provider is unknown or not configured
    """
    # Return cached provider if available
    if provider_name in _providers:
        return _providers[provider_name]

    # Create new provider
    provider: EmailProvider
    if provider_name == "brevo":
        from mailler.services.providers.brevo import BrevoProvider

        provider = BrevoProvider()
    elif provider_name == "sendgrid":
        from mailler.services.providers.sendgrid import SendGridProvider

        provider = SendGridProvider()
    elif provider_name == "ses":
        from mailler.services.providers.ses import SESProvider

        provider = SESProvider()
    elif provider_name == "protonmail":
        from mailler.services.providers.protonmail import ProtonmailProvider

        provider = ProtonmailProvider()
    else:
        raise ValueError(f"Unknown email provider: {provider_name}")

    # Check if provider is configured
    if not provider.is_configured:
        logger.warning(
            "Provider not configured",
            extra={"provider": provider_name},
        )
        raise ValueError(f"Provider '{provider_name}' is not properly configured")

    # Cache and return
    _providers[provider_name] = provider
    logger.info("Created email provider", extra={"provider": provider_name})
    return provider


def get_available_providers() -> list[str]:
    """Get list of available (configured) providers.

    Returns:
        List of provider names that are properly configured
    """
    available = []

    for name in PROVIDER_CLASSES:
        try:
            provider = get_provider(name)
            if provider.is_configured:
                available.append(name)
        except ValueError:
            pass

    return available
