# reachy-mini-api

Internal FastAPI service used by the Reachy Mini robot. Workspace member of the
`website` monorepo (distribution `reachy-mini-api`, import package
`reachy_mini_api`).

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint (hidden from Swagger) |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

## Development

```bash
uv sync --package reachy-mini-api
uv run --package reachy-mini-api uvicorn reachy_mini_api.main:app --reload --port 8002
uv run --package reachy-mini-api pytest apps/reachy-mini-api
uv run --package reachy-mini-api behave apps/reachy-mini-api/features
```

Configuration is read from environment variables (a `.env` file is loaded
when present). The documentation lives under `docs/apps/reachy-mini-api/`.
