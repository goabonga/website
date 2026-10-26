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

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `billing:platform:write` - checked by 3 routes
- `billing:platform:read` - checked by 2 routes

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
