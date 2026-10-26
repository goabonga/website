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

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |
| POST | `/platform/saas` | scope `billing:platform:write` | Create a new SaaS application |
| GET | `/platform/saas` | scope `billing:platform:read` | List all SaaS applications |
| GET | `/platform/saas/{saas_id}` | scope `billing:platform:read` | Get a SaaS application by ID |
| PATCH | `/platform/saas/{saas_id}` | scope `billing:platform:write` | Update a SaaS application |
| POST | `/platform/saas/{saas_id}/sync-stripe` | scope `billing:platform:write` | Sync products and prices to Stripe |
| POST | `/platform/{saas_id}/products` | scope `billing:platform:write` | Create a new product (syncs to Stripe) |
| GET | `/platform/{saas_id}/products` | scope `billing:platform:read` | List all products for a SaaS app |
| GET | `/platform/{saas_id}/products/{product_id}` | scope `billing:platform:read` | Get a product by ID |
| PATCH | `/platform/{saas_id}/products/{product_id}` | scope `billing:platform:write` | Update a product (syncs to Stripe) |
| POST | `/platform/{saas_id}/products/{product_id}/prices` | scope `billing:platform:write` | Create a new price for a product (syncs to Stripe) |
| GET | `/platform/{saas_id}/products/{product_id}/prices` | scope `billing:platform:read` | List all prices for a product |
| GET | `/platform/{saas_id}/products/{product_id}/prices/{price_id}` | scope `billing:platform:read` | Get a price by ID |
| PATCH | `/platform/{saas_id}/products/{product_id}/prices/{price_id}` | scope `billing:platform:write` | Update a price (limited fields - Stripe prices are mostly immutable) |
| POST | `/platform/{saas_id}/customers` | scope `billing:platform:write` | Create a new customer (syncs to Stripe) |
| GET | `/platform/{saas_id}/customers` | scope `billing:platform:read` | List all customers for a SaaS app |
| GET | `/platform/{saas_id}/customers/{customer_id}` | scope `billing:platform:read` | Get a customer by ID |
| PATCH | `/platform/{saas_id}/customers/{customer_id}` | scope `billing:platform:write` | Update a customer (syncs to Stripe) |
| GET | `/platform/{saas_id}/customers/{customer_id}/portal` | scope `billing:platform:read` | Generate a Customer Portal URL for managing billing |
| GET | `/platform/{saas_id}/subscriptions` | scope `billing:platform:read` | List all subscriptions for a SaaS app |
| GET | `/platform/{saas_id}/customers/{customer_id}/subscriptions` | scope `billing:platform:read` | List all subscriptions for a customer |
| GET | `/platform/{saas_id}/external/{external_id}/subscription` | scope `billing:platform:read` | Get the active subscription for a customer by external_id |
| GET | `/platform/{saas_id}/subscriptions/{subscription_id}` | scope `billing:platform:read` | Get a subscription by ID |
| POST | `/platform/{saas_id}/customers/{customer_id}/subscriptions` | scope `billing:platform:write` | Create a new subscription for a customer (syncs to Stripe) |
| PATCH | `/platform/{saas_id}/subscriptions/{subscription_id}` | scope `billing:platform:write` | Update a subscription (syncs to Stripe) |
| DELETE | `/platform/{saas_id}/subscriptions/{subscription_id}` | scope `billing:platform:write` | Cancel a subscription (syncs to Stripe) |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/sync` | scope `billing:platform:write` | Sync subscription data from Stripe |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview` | scope `billing:platform:read` | Preview proration costs for upgrading a subscription |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/upgrade` | scope `billing:platform:write` | Upgrade a subscription to a new plan with proration |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/cancel` | scope `billing:platform:write` | Cancel a subscription, at the end of the paid period by default |
| POST | `/platform/{saas_id}/subscriptions/{subscription_id}/reactivate` | scope `billing:platform:write` | Undo a cancellation scheduled for the end of the period |
| GET | `/plans/{app_slug}` | public | List all plans for a SaaS application |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `billing:platform:write` - checked by 16 routes
- `billing:platform:read` - checked by 14 routes

## Usage

All commands run from the repository root.

```bash
# Install the workspace member and the dev tools
uv sync --package billing --group dev

# Start local PostgreSQL and Redis (ports 5435 and 6382)
docker compose -f apps/billing/compose.yml up -d

# Apply the database migrations
uv run --package billing alembic -c apps/billing/alembic.ini upgrade head

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
