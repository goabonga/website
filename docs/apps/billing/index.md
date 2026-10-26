# billing

Multi-SaaS Stripe billing platform. A single Stripe account serves several
SaaS applications: every Stripe object carries `metadata.saas_id`, so
products, prices, customers and subscriptions of each tenant stay isolated.
The service manages the catalog, creates Checkout sessions, tracks metered
usage and keeps local subscription state in sync through Stripe webhooks.
It is an internal service, reachable only from the VPN subnet or through its
Unix socket.

Workspace member: `apps/billing` (distribution `billing`, import package
`billing`, FastAPI application `billing.main:app`).

## Features

The application is built as a sequence of features. Each page below
documents one of them: what it adds, how it is configured and how it is
tested.

| # | Feature | Summary |
|---|---------|---------|
| 1 | [Foundation](01-foundation.md) | Settings, logging, database session, health endpoint |
| 2 | [Authentication](02-authentication.md) | JWT validation, introspection, token exchange, scopes |
| 3 | [Data model](03-data-model.md) | SQLAlchemy models and Alembic migrations |
| 4 | [Stripe service](04-stripe-service.md) | Stripe SDK wrapper enforcing `saas_id` metadata |
| 5 | [SaaS applications](05-saas-apps.md) | Onboarding and management of tenants |
| 6 | [Products](06-products.md) | Product catalog per tenant |
| 7 | [Prices](07-prices.md) | One-time, recurring and metered prices |
| 8 | [Customers](08-customers.md) | Customers synchronized with Stripe |
| 9 | [Subscriptions](09-subscriptions.md) | Lifecycle, sync and upgrades with proration |
| 9a | [Subscription actions](09a-subscription-actions.md) | Cancel at period end or immediately, reactivate |
| 10 | [Plans](10-plans.md) | Public pricing plans |
| 11 | [Checkout](11-checkout.md) | Stripe Checkout sessions |
| 12 | [Usage](12-usage.md) | Metered usage events |
| 12a | [Client partitioning](12a-client-partitioning.md) | OAuth client to SaaS bindings, admin scope, onboarding |
| 13 | [Webhooks](13-webhooks.md) | Stripe events and tenant notifications |
| 14 | [Background tasks](14-background-tasks.md) | Celery tasks and beat schedule |
| 14a | [Notification delivery](14a-webhook-delivery.md) | Queued, retried and idempotent notifications to tenants |
| 15 | [Deployment](15-deployment.md) | Ansible deployment, secrets and dependencies |

## Running the tests

All commands run from the repository root.

```bash
uv run --package billing --group dev pytest apps/billing
uv run --package billing --group dev behave apps/billing/features
```

The pytest suite mocks the database session, Stripe and the authentication
layer. The behave scenarios run in the same process: the FastAPI application
is called through an ASGI transport, the database is an in-memory SQLite
engine, token validation is faked and Stripe is replaced by a mock, so
neither server, PostgreSQL, Redis nor network access is needed.
