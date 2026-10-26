# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the subscription cancel and reactivate actions."""

from unittest.mock import MagicMock

from behave import given


@given("Stripe runs subscriptions until the end of the paid period")
def step_stripe_period_semantics(context):
    """Make the Stripe mock behave like Stripe for cancellations.

    Cancelling at the period end leaves the subscription ``active`` and flags
    it; an immediate cancellation ends it; clearing the flag keeps it active.
    The mock is restored after the scenario.
    """
    mock = context.stripe_mock

    def cancel(**kwargs):
        immediately = kwargs["immediately"]
        return MagicMock(
            status="canceled" if immediately else "active",
            cancel_at_period_end=not immediately,
        )

    def update(**kwargs):
        return MagicMock(
            status="active", cancel_at_period_end=kwargs.get("cancel_at_period_end", False)
        )

    mock.cancel_subscription.side_effect = cancel
    mock.update_subscription.side_effect = update
    context.add_cleanup(setattr, mock.cancel_subscription, "side_effect", None)
    context.add_cleanup(setattr, mock.update_subscription, "side_effect", None)
