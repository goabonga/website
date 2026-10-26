# billing

Multi-SaaS Stripe billing platform. A FastAPI service that manages
products, prices, customers, subscriptions and metered usage for several
SaaS applications from a single Stripe account. Each SaaS application is
isolated through `metadata.saas_id` on every Stripe object.

This package is a member of the uv workspace of the `website` monorepo.
Full documentation lives in `docs/apps/billing/`.

## Features

- Health endpoint, environment-driven settings and dual-stream logging
- OAuth2 / OIDC authentication with scope checks (`billing:*`)
- PostgreSQL data model with Alembic migrations
- Stripe service wrapper enforcing the `saas_id` metadata
- Onboarding of SaaS applications
- Product catalog per SaaS application
- One-time, recurring and metered prices
- Customers synchronized with Stripe
- Subscription lifecycle (create, update, cancel, upgrade with proration preview)
- Cancel and reactivate actions for subscriptions
- Public pricing plans per SaaS application
- Stripe Checkout sessions
- Metered usage events
- Partitioning of the API per SaaS application: OAuth clients are bound to the applications they may act on, with an admin API and the `billing-admin` command
- Stripe webhook processing and subscription events pushed to each SaaS application

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |
| POST | `/platform/saas` | scope `billing:admin` (`PARTITION_ADMIN_SCOPE`) | Create a new SaaS application (admin scope: it is not bound to any client yet) |
| GET | `/platform/saas` | scope `billing:platform:read`; lists the apps the client is bound to | List the SaaS applications the caller may act on (all of them for the admin scope) |
| GET | `/platform/saas/{saas_id}` | scope `billing:platform:read`; client bound to the app | Get a SaaS application by ID |
| PATCH | `/platform/saas/{saas_id}` | scope `billing:platform:write`; client bound to the app | Update a SaaS application |
| POST | `/platform/saas/{saas_id}/sync-stripe` | scope `billing:platform:write`; client bound to the app | Sync products and prices to Stripe |
| GET | `/platform/saas/{saas_id}/clients` | scope `billing:admin` (`PARTITION_ADMIN_SCOPE`) | List the OAuth clients bound to a SaaS application |
| PUT | `/platform/saas/{saas_id}/clients/{client_id}` | scope `billing:admin` (`PARTITION_ADMIN_SCOPE`) | Bind an OAuth client to a SaaS application (idempotent) |
| DELETE | `/platform/saas/{saas_id}/clients/{client_id}` | scope `billing:admin` (`PARTITION_ADMIN_SCOPE`) | Remove the binding of an OAuth client to a SaaS application |
| GET | `/platform/clients/{client_id}/saas` | scope `billing:admin` (`PARTITION_ADMIN_SCOPE`) | List the SaaS applications an OAuth client is bound to |
| POST | `/platform/{saas_id}/products` | scope `billing:platform:write`; client bound to the app | Create a new product (syncs to Stripe) |
| GET | `/platform/{saas_id}/products` | scope `billing:platform:read`; client bound to the app | List all products for a SaaS app |
| GET | `/platform/{saas_id}/products/{product_id}` | scope `billing:platform:read`; client bound to the app | Get a product by ID |
| PATCH | `/platform/{saas_id}/products/{product_id}` | scope `billing:platform:write`; client bound to the app | Update a product (syncs to Stripe) |
| POST | `/platform/{saas_id}/products/{product_id}/prices` | scope `billing:platform:write`; client bound to the app | Create a new price for a product (syncs to Stripe) |
| GET | `/platform/{saas_id}/products/{product_id}/prices` | scope `billing:platform:read`; client bound to the app | List all prices for a product |
| GET | `/platform/{saas_id}/products/{product_id}/prices/{price_id}` | scope `billing:platform:read`; client bound to the app | Get a price by ID |
| PATCH | `/platform/{saas_id}/products/{product_id}/prices/{price_id}` | scope `billing:platform:write`; client bound to the app | Update a price (limited fields - Stripe prices are mostly immutable) |
| POST | `/platform/{saas_id}/customers` | scope `billing:platform:write`; client bound to the app | Create a new customer (syncs to Stripe) |
| GET | `/platform/{saas_id}/customers` | scope `billing:platform:read`; client bound to the app | List all customers for a SaaS app |
| GET | `/platform/{saas_id}/customers/{customer_id}` | scope `billing:platform:read`; client bound to the app | Get a customer by ID |
| PATCH | `/platform/{saas_id}/customers/{customer_id}` | scope `billing:platform:write`; client bound to the app | Update a customer (syncs to Stripe) |
| GET | `/platform/{saas_id}/customers/{customer_id}/portal` | scope `billing:platform:read`; client bound to the app | Generate a Customer Portal URL for managing billing |
| GET | `/platform/{saas_id}/subscriptions` | scope `billing:platform:read`; client bound to the app | List all subscriptions for a SaaS app |
| GET | `/platform/{saas_id}/customers/{customer_id}/subscriptions` | scope `billing:platform:read`; client bound to the app | List all subscriptions for a customer |
| GET | `/platform/{saas_id}/external/{external_id}/subscription` | scope `billing:platform:read`; client bound to the app | Get the active subscription for a customer by external_id |
| GET | `/platform/{saas_id}/subscriptions/{subscription_id}` | scope `billing:platform:read`; client bound to the app | Get a subscription by ID |
| POST | `/platform/{saas_id}/customers/{customer_id}/subscriptions` | scope `billing:platform:write`; client bound to the app | Create a new subscription for a customer (syncs to Stripe) |
| PATCH | `/platform/{saas_id}/subscriptions/{subscription_id}` | scope `billing:platform:write`; client bound to the app | Update a subscription (syncs to Stripe) |
| DELETE | `/platform/{saas_id}/subscriptions/{subscription_id}` | scope `billing:platform:write`; client bound to the app | Cancel a subscription (syncs to Stripe) |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/sync` | scope `billing:platform:write`; client bound to the app | Sync subscription data from Stripe |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview` | scope `billing:platform:read`; client bound to the app | Preview proration costs for upgrading a subscription |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/upgrade` | scope `billing:platform:write`; client bound to the app | Upgrade a subscription to a new plan with proration |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/cancel` | scope `billing:platform:write`; client bound to the app | Cancel a subscription, at the end of the paid period by default |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/reactivate` | scope `billing:platform:write`; client bound to the app | Undo a cancellation scheduled for the end of the period |
| POST | `/usage/{saas_id}/report` | scope `billing:usage:write`; client bound to the app | Report a single usage event |
| POST | `/usage/{saas_id}/batch` | scope `billing:usage:write`; client bound to the app | Report multiple usage events in a batch |
| GET | `/plans/{app_slug}` | scope `billing:platform:read` and client bound to the app; public when `PLANS_PUBLIC` is enabled | List all plans for a SaaS application |
| POST | `/checkout/session` | scope `billing:checkout:write`; client bound to the requested app | Create a Stripe Checkout Session |
| POST | `/webhooks/stripe` | public; `Stripe-Signature` checked (`STRIPE_WEBHOOK_SECRET`), plus the scope of `STRIPE_WEBHOOK_REQUIRED_SCOPE` when set | Receive and process Stripe webhook events |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

Routes that target a SaaS application are partitioned: a client acts only on the applications it is bound to, and the scope of the `PARTITION_ADMIN_SCOPE` setting (default `billing:admin`) bypasses the binding. A client bound to no application is denied unless `PARTITION_ALLOW_UNBOUND` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `billing:admin` - checked by 5 routes
- `billing:platform:read` - checked by 15 routes
- `billing:platform:write` - checked by 15 routes
- `billing:usage:write` - checked by 2 routes
- `billing:checkout:write` - checked by 1 route

## Usage

All commands run from the repository root.

```bash
# Install the workspace member and the dev tools
uv sync --package billing --group dev

# Start local PostgreSQL and Redis (ports 5435 and 6382)
docker compose -f apps/billing/compose.yml up -d

# Apply the database migrations
uv run --package billing alembic -c apps/billing/alembic.ini upgrade head

# Create the first SaaS application and bind the OAuth client that will manage it
uv run --package billing billing-admin saas create --name "Example App" --slug example-app
uv run --package billing billing-admin client bind --saas example-app --client-id <oauth client id>

# Start the API
uv run --package billing uvicorn billing.main:app --reload --port 8000
```

## Development

```bash
uv run --package billing --group dev pytest apps/billing
uv run --package billing --group dev behave apps/billing/features
uv run ruff check apps/billing
uv run ruff format --check apps/billing
```

## License

MIT
