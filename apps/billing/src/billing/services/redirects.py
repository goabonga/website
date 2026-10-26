# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Redirect targets accepted by a SaaS application.

Stripe sends the customer back to a URL chosen by the caller once a Checkout
session or a portal session ends. Each SaaS application lists the URL
prefixes it accepts (``SaasApp.checkout_url_allowlist``); any other target is
refused so that a billing client cannot send customers to an arbitrary site.
"""

from collections.abc import Sequence
from urllib.parse import urlsplit

from billing.config import settings
from billing.models import SaasApp

_DEFAULT_PORTS = {"http": 80, "https": 443}


class RedirectNotAllowed(ValueError):
    """Raised when a redirect URL is not accepted by the SaaS application."""


def _origin(url: str) -> tuple[str, str, int | None, str] | None:
    """Split a URL into (scheme, host, port, path), or None if it is not usable."""
    parts = urlsplit(url.strip())
    if parts.scheme not in _DEFAULT_PORTS or not parts.hostname or parts.username or parts.password:
        return None
    try:
        port = parts.port or _DEFAULT_PORTS[parts.scheme]
    except ValueError:
        return None
    return parts.scheme, parts.hostname.lower(), port, parts.path.rstrip("/")


def matches_allowlist(url: str, allowlist: Sequence[str]) -> bool:
    """Tell whether ``url`` is covered by one of the allow-list prefixes.

    A prefix covers a URL when scheme, host and port are equal and the
    path of the prefix is the path of the URL or one of its parent segments
    (``https://app.example.test/billing`` covers
    ``https://app.example.test/billing/done`` but not
    ``https://app.example.test/billing-other``). A prefix without path
    covers the whole origin.
    """
    target = _origin(url)
    if target is None:
        return False
    scheme, host, port, path = target
    for entry in allowlist:
        prefix = _origin(entry)
        if prefix is None:
            continue
        p_scheme, p_host, p_port, p_path = prefix
        if (scheme, host, port) != (p_scheme, p_host, p_port):
            continue
        if not p_path or path == p_path or path.startswith(p_path + "/"):
            return True
    return False


def ensure_allowed_redirect(saas_app: SaasApp, url: str, field: str) -> None:
    """Check a redirect URL against the allow-list of a SaaS application.

    When the SaaS application has no allow-list, the URL is refused unless
    ``REDIRECT_ALLOWLIST_REQUIRED`` is disabled.

    Args:
        saas_app: The SaaS application the request is made for.
        url: The redirect URL given by the caller.
        field: Name of the request field, used in the error message.

    Raises:
        RedirectNotAllowed: If the URL is not accepted.
    """
    allowlist = saas_app.checkout_url_allowlist
    if not allowlist:
        if settings.redirect_allowlist_required:
            raise RedirectNotAllowed(
                f"{field} is refused: SaaS app '{saas_app.slug}' has no checkout_url_allowlist"
            )
        return
    if not matches_allowlist(url, allowlist):
        raise RedirectNotAllowed(f"{field} is not in the checkout_url_allowlist of the SaaS app")
