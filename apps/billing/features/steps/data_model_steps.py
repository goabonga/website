# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the data model.

The models are exercised against the in-memory SQLite database created by the
behave environment.
"""

from datetime import UTC, datetime

from behave import given, then, when
from billing.models import (
    BillingPrice,
    BillingProduct,
    Customer,
    SaasApp,
    Subscription,
    UsageEvent,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


async def _store(context, *objects):
    """Persist objects in a fresh session and return their identifiers."""
    async with context.session_factory() as session:
        session.add_all(objects)
        await session.commit()
        return [obj.id for obj in objects]


async def _fetch(context, model, **filters):
    """Load a single row of ``model`` matching ``filters`` in a fresh session."""
    async with context.session_factory() as session:
        result = await session.execute(select(model).filter_by(**filters))
        return result.scalar_one()


@given('a stored SaaS application "{name}" with slug "{slug}"')
def step_store_saas(context, name, slug):
    """Store a SaaS application."""
    (context.saas_id,) = _run(context, _store(context, SaasApp(name=name, slug=slug)))


@when('I reload the SaaS application "{slug}"')
def step_reload_saas(context, slug):
    """Reload the SaaS application from the database."""
    context.saas = _run(context, _fetch(context, SaasApp, slug=slug))


@then("the SaaS application is active")
def step_saas_active(context):
    assert context.saas.is_active is True


@then("the SaaS application has an identifier and a creation date")
def step_saas_identity(context):
    assert context.saas.id
    assert context.saas.created_at is not None


@when('I try to store another SaaS application "{name}" with slug "{slug}"')
def step_store_duplicate_saas(context, name, slug):
    """Try to store a SaaS application and remember any integrity error."""
    context.integrity_error = None
    try:
        _run(context, _store(context, SaasApp(name=name, slug=slug)))
    except IntegrityError as exc:
        context.integrity_error = exc


@then("the database rejects it as a duplicate")
def step_duplicate_rejected(context):
    assert context.integrity_error is not None, "Duplicate slug was accepted"


@given('a stored product "{name}" with a price for the SaaS application')
def step_store_product_and_price(context, name):
    """Store a product and a price using the model defaults."""
    (product_id,) = _run(
        context,
        _store(
            context,
            BillingProduct(
                saas_app_id=context.saas_id,
                stripe_product_id="prod_model",
                slug=name.lower(),
                name=name,
            ),
        ),
    )
    _run(
        context,
        _store(context, BillingPrice(product_id=product_id, stripe_price_id="price_model")),
    )


@when("I reload the price")
def step_reload_price(context):
    context.price = _run(context, _fetch(context, BillingPrice, stripe_price_id="price_model"))


@then('the price is a recurring licensed price in "{currency}"')
def step_price_defaults(context, currency):
    assert context.price.billing_type == "recurring"
    assert context.price.usage_type == "licensed"
    assert context.price.currency == currency
    assert context.price.recurring_interval_count == 1


@given('a stored customer "{external_id}" for the SaaS application')
def step_store_customer(context, external_id):
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


@when("I soft delete the customer")
def step_soft_delete_customer(context):
    async def _delete():
        async with context.session_factory() as session:
            customer = await session.get(Customer, context.customer_id)
            customer.deleted_at = datetime.now(UTC)
            await session.commit()

    _run(context, _delete())


@then("the customer is flagged as deleted")
def step_customer_deleted(context):
    customer = _run(context, _fetch(context, Customer, id=context.customer_id))
    assert customer.is_deleted is True


@given("a stored subscription for the customer")
def step_store_subscription(context):
    (context.subscription_id,) = _run(
        context,
        _store(
            context,
            Subscription(customer_id=context.customer_id, stripe_subscription_id="sub_model"),
        ),
    )


@when("I store a usage event of {quantity:d} units for the subscription")
def step_store_usage_event(context, quantity):
    _run(
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


@then('the subscription status is "{status}"')
def step_subscription_status(context, status):
    subscription = _run(context, _fetch(context, Subscription, id=context.subscription_id))
    assert subscription.status == status


@then('the usage event status is "{status}"')
def step_usage_event_status(context, status):
    event = _run(context, _fetch(context, UsageEvent, subscription_id=context.subscription_id))
    assert event.status == status


# -- Scoping of plan slugs and idempotency keys --------------------------------


@given('a tenant "{name}" with slug "{slug}" and customer "{external_id}"')
def step_store_saas_with_customer(context, name, slug, external_id):
    """Store a SaaS application with one customer and one subscription, kept by slug."""
    (saas_id,) = _run(context, _store(context, SaasApp(name=name, slug=slug)))
    (customer_id,) = _run(
        context,
        _store(
            context,
            Customer(
                saas_app_id=saas_id,
                external_id=external_id,
                stripe_customer_id=f"cus_{slug}",
                email=f"{external_id}@example.com",
            ),
        ),
    )
    (subscription_id,) = _run(
        context,
        _store(
            context,
            Subscription(customer_id=customer_id, stripe_subscription_id=f"sub_{slug}"),
        ),
    )
    context.tenants = getattr(context, "tenants", {})
    context.tenants[slug] = {"saas_id": saas_id, "subscription_id": subscription_id}


def _try_store(context, obj):
    """Store an object, remembering an integrity error without losing an earlier one."""
    if not hasattr(context, "integrity_error"):
        context.integrity_error = None
    try:
        _run(context, _store(context, obj))
    except IntegrityError as exc:
        context.integrity_error = exc


@when('I store a product with plan slug "{plan}" for "{slug}"')
def step_store_plan(context, plan, slug):
    tenant = context.tenants[slug]
    count = getattr(context, "plan_counter", 0) + 1
    context.plan_counter = count
    _try_store(
        context,
        BillingProduct(
            saas_app_id=tenant["saas_id"],
            stripe_product_id=f"prod_scope_{count}",
            slug=plan,
            name=plan.title(),
        ),
    )


@when('I store a usage event with idempotency key "{key}" for "{slug}"')
def step_store_keyed_usage(context, key, slug):
    tenant = context.tenants[slug]
    _try_store(
        context,
        UsageEvent(
            saas_app_id=tenant["saas_id"],
            subscription_id=tenant["subscription_id"],
            quantity=1,
            timestamp=datetime.now(UTC),
            idempotency_key=key,
        ),
    )


@then("the database accepts it")
def step_accepted(context):
    assert getattr(context, "integrity_error", None) is None, f"Rejected: {context.integrity_error}"
