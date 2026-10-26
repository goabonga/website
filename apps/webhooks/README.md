# webhooks

Minimal FastAPI gateway for receiving external webhooks and forwarding the
events to internal services. Workspace member of the `website` monorepo
(distribution `webhooks`, import package `webhooks`).

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring and load balancer probes |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

## Configuration

Read from the environment (a `.env` file is loaded when present).

| Variable | Description | Default |
| --- | --- | --- |
| `APP_NAME` | Application name | `Webhooks` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DOCS_ENABLED` | Expose Swagger, ReDoc and OpenAPI endpoints | `false` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON list); CORS is off when empty | `[]` |
| `CORS_CREDENTIALS` | Allow credentials in CORS requests | `true` |
| `CORS_METHODS` | Allowed HTTP methods (JSON list) | `["*"]` |
| `CORS_HEADERS` | Allowed headers (JSON list) | `["*"]` |

## Logging

Records are split over two streams for systemd: `DEBUG` and `INFO` go to
stdout, `WARNING`, `ERROR` and `CRITICAL` go to stderr. The level comes from
`LOG_LEVEL` and logging is configured when the application starts.

## Development

```bash
uv sync --package webhooks
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
