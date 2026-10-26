# reachy-mini-api

Internal FastAPI service used by the Reachy Mini robot. Workspace member of the
`website` monorepo (distribution `reachy-mini-api`, import package
`reachy_mini_api`).

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint (hidden from Swagger) |
| GET | `/api/reports/daily` | scope `reachy:reports:read` | Get today's daily report for Reachy to announce |
| GET | `/api/reports/quick` | scope `reachy:reports:read` | Get a quick update for immediate announcement |
| GET | `/api/reports/notifications` | scope `reachy:notifications:read` | Get pending notifications |
| GET | `/api/status/server` | scope `reachy:status:read` | Get server status information |
| GET | `/api/status/services` | scope `reachy:status:read` | Get status of monitored services |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `reachy:reports:read` - checked by 2 routes
- `reachy:notifications:read` - checked by 1 route
- `reachy:status:read` - checked by 2 routes

## Development

```bash
uv sync --package reachy-mini-api
uv run --package reachy-mini-api uvicorn reachy_mini_api.main:app --reload --port 8002
uv run --package reachy-mini-api pytest apps/reachy-mini-api
uv run --package reachy-mini-api behave apps/reachy-mini-api/features
```

Configuration is read from environment variables (a `.env` file is loaded
when present). The documentation lives under `docs/apps/reachy-mini-api/`.
