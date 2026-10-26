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
| `OAUTH2_TOKEN_URL` | Token endpoint of the authorization server | - |
| `OAUTH2_CLIENT_ID` | OAuth2 client identifier | - |
| `OAUTH2_CLIENT_SECRET` | OAuth2 client secret (also read from systemd credentials) | - |

## Downstream authentication

When the three `OAUTH2_*` variables are set, the gateway acquires an access
token with the `client_credentials` grant and sends it as a `Bearer` token
to internal services. Without OAuth2 configuration a static bearer token is
used when one is provided.

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
