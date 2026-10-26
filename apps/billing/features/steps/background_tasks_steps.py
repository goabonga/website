# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the Celery background tasks.

Tasks are executed eagerly with ``Task.apply()``; the database is the
in-memory SQLite engine of the behave environment and Stripe is mocked.
"""

from datetime import UTC, datetime, timedelta

from behave import given, then, when
from billing.celery import celery_app
from billing.models import (
    BillingPrice,
    BillingProduct,
    Customer,
    SaasApp,
    Subscription,
    UsageEvent,
    UsageEventStatus,
)
from billing.tasks.stripe_sync_tasks import sync_all_products_to_stripe
from billing.tasks.usage_tasks import cleanup_old_usage_events, report_pending_usage
from sqlalchemy import func, select


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


async def _store(context, *objects):
    """Persist objects in a fresh session and return their identifiers."""
    async with context.session_factory() as session:
        session.add_all(objects)
        await session.commit()
        return [obj.id for obj in objects]


@given('a SaaS application with slug "{slug}" and a customer "{external_id}"')
def step_saas_and_customer(context, slug, external_id):
    (context.saas_id,) = _run(context, _store(context, SaasApp(name="Tasks App", slug=slug)))
    (context.customer_id,) = _run(
        context,
        _store(
            context,
            Customer(
                saas_app_id=context.saas_id,
                external_id=external_id,
                stripe_customer_id=f"cus_{external_id}",
                email=f"{external_id}@example.com",
            ),
        ),
    )


@given("a subscription with a subscription item")
def step_subscription_with_item(context):
    (context.subscription_id,) = _run(
        context,
        _store(
            context,
            Subscription(
                customer_id=context.customer_id,
                stripe_subscription_id="sub_tasks",
                stripe_subscription_item_id="si_tasks",
            ),
        ),
    )


@given("a subscription without a subscription item")
def step_subscription_without_item(context):
    (context.subscription_id,) = _run(
        context,
        _store(
            context,
            Subscription(customer_id=context.customer_id, stripe_subscription_id="sub_tasks"),
        ),
    )


@given("a pending usage event of {quantity:d} units")
def step_pending_event(context, quantity):
    (context.event_id,) = _run(
        context,
        _store(
            context,
            UsageEvent(
                saas_app_id=context.saas_id,
                subscription_id=context.subscription_id,
                quantity=quantity,
                timestamp=datetime.now(UTC),
            ),
        ),
    )


@given("a reported usage event of {quantity:d} units from {days:d} days ago")
def step_old_reported_event(context, quantity, days):
    moment = datetime.now(UTC) - timedelta(days=days)
    (context.event_id,) = _run(
        context,
        _store(
            context,
            UsageEvent(
                saas_app_id=context.saas_id,
                subscription_id=context.subscription_id,
                quantity=quantity,
                timestamp=moment,
                status=UsageEventStatus.REPORTED,
                reported_at=moment,
            ),
        ),
    )


@given('a product "{name}" without a real Stripe identifier and a price of {amount:d} cents')
def step_placeholder_product(context, name, amount):
    (product_id,) = _run(
        context,
        _store(
            context,
            BillingProduct(
                saas_app_id=context.saas_id,
                stripe_product_id="prod_placeholder",
                slug=name.lower(),
                name=name,
            ),
        ),
    )
    _run(
        context,
        _store(
            context,
            BillingPrice(
                product_id=product_id, stripe_price_id="price_placeholder", unit_amount=amount
            ),
        ),
    )


@when("I run the pending usage reporting task")
def step_run_report(context):
    context.stripe_mock.report_usage.return_value = {"id": "mbur_bdd"}
    context.task_result = report_pending_usage.apply(kwargs={"batch_size": 10}).get()


@when("I run the usage cleanup task for events older than {days:d} days")
def step_run_cleanup(context, days):
    context.task_result = cleanup_old_usage_events.apply(kwargs={"days_old": days}).get()


@when("I run the Stripe catalog sync task")
def step_run_sync(context):
    context.task_result = sync_all_products_to_stripe.apply().get()


@then("the task result should be processed {processed:d}, success {success:d}, failed {failed:d}")
def step_check_report(context, processed, success, failed):
    assert context.task_result == {"processed": processed, "success": success, "failed": failed}


@then('the usage event should be "{status}"')
def step_check_event_status(context, status):
    async def _status():
        async with context.session_factory() as session:
            return (
                await session.execute(
                    select(UsageEvent.status).where(UsageEvent.id == context.event_id)
                )
            ).scalar_one()

    assert _run(context, _status()) == status


@then("the cleanup task should delete {count:d} event")
def step_check_cleanup(context, count):
    assert context.task_result == {"deleted": count}

    async def _remaining():
        async with context.session_factory() as session:
            return (
                await session.execute(select(func.count()).select_from(UsageEvent))
            ).scalar_one()

    assert _run(context, _remaining()) == 0


@then("the sync task should report {products:d} product and {prices:d} price synced")
def step_check_sync(context, products, prices):
    assert context.task_result["products_synced"] == products
    assert context.task_result["prices_synced"] == prices
    assert context.task_result["errors"] == []


@then("the beat schedule should contain the tasks")
def step_check_beat(context):
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    expected = {row["task"] for row in context.table}
    assert expected <= scheduled, f"Missing: {expected - scheduled}"


@given('a pending usage event of {quantity:d} units with the idempotency key "{key}"')
def step_pending_event_with_key(context, quantity, key):
    (context.event_id,) = _run(
        context,
        _store(
            context,
            UsageEvent(
                saas_app_id=context.saas_id,
                subscription_id=context.subscription_id,
                quantity=quantity,
                timestamp=datetime.now(UTC),
                idempotency_key=key,
            ),
        ),
    )


@then('Stripe should receive the idempotency key scoped to the SaaS app for "{key}"')
def step_scoped_key(context, key):
    import hashlib

    sent = context.stripe_mock.report_usage.call_args.kwargs["idempotency_key"]
    assert sent == hashlib.sha256(f"{context.saas_id}:{key}".encode()).hexdigest(), sent
    assert sent != key


@then("the beat schedule should use the configured intervals")
def step_beat_intervals(context):
    from billing.celery import celery_app
    from billing.config import settings

    schedule = celery_app.conf.beat_schedule
    assert schedule["report-pending-usage"]["schedule"] == settings.usage_report_interval
    assert schedule["cleanup-old-usage-events"]["schedule"] == settings.usage_cleanup_interval
    assert schedule["sync-products-to-stripe"]["schedule"] == settings.stripe_sync_interval
