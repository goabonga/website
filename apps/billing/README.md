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

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

## Usage

All commands run from the repository root.

```bash
# Install the workspace member and the dev tools
uv sync --package billing --group dev

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
