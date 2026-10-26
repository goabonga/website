# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The billing service for the browser scenarios.

It answers what the scenario declares (plans, subscription, proration quote, upgrade result)
or fails when told to, and records the calls the pages make. Its checkout sends the customer
straight back to the success address, as a customer who paid would be.
"""

from types import SimpleNamespace


class Billing:
    """In-memory stand-in for ``BillingClient``."""

    is_configured = True
    app_slug = ""

    def __init__(self):
        self.plans = []
        self.subscription = None
        self.preview = None
        self.upgrade_result = None
        self.error = None
        self.checkout_calls = []
        self.upgrade_calls = []
        self.cancel_calls = []
        self.reactivate_calls = []

    def _fail_when_told_to(self):
        if self.error is not None:
            raise self.error

    async def get_plans(self):
        self._fail_when_told_to()
        return self.plans

    async def get_tenant_subscription(self, tenant_id):
        self._fail_when_told_to()
        return self.subscription

    async def create_checkout_session(self, **kwargs):
        self._fail_when_told_to()
        self.checkout_calls.append(kwargs)
        return SimpleNamespace(session_id="checkout", url=kwargs["success_url"])

    async def preview_upgrade(self, **kwargs):
        self._fail_when_told_to()
        return self.preview

    async def upgrade_subscription(self, **kwargs):
        self._fail_when_told_to()
        self.upgrade_calls.append(kwargs)
        return self.upgrade_result

    async def cancel_subscription(self, *args, **kwargs):
        self._fail_when_told_to()
        self.cancel_calls.append((args, kwargs))
        return SimpleNamespace(success=True, cancel_at=None)

    async def reactivate_subscription(self, *args, **kwargs):
        self._fail_when_told_to()
        self.reactivate_calls.append((args, kwargs))
        return SimpleNamespace(success=True)
