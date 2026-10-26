# billing

Multi-SaaS Stripe billing platform. A FastAPI service that manages
products, prices, customers, subscriptions and metered usage for several
SaaS applications from a single Stripe account. Each SaaS application is
isolated through `metadata.saas_id` on every Stripe object.

This package is a member of the uv workspace of the `website` monorepo.

## Features

- Health endpoint, environment-driven settings and dual-stream logging

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

## License

MIT
