# Application foundation

The foundation provides the workspace member, the settings class, the
FastAPI application object and the health endpoint. Every later feature
plugs into it.

## What it does

- Declares the `webhooks` distribution (hatchling build, src layout, Python
  3.11 or later) with its import package `webhooks`.
- Loads settings from the environment (and from a `.env` file when present).
  Variable names are case-insensitive.
- Creates the FastAPI application `webhooks.main:app`. Swagger, ReDoc and
  the OpenAPI schema are disabled unless `DOCS_ENABLED` is true; when it is
  disabled `docs_url`, `redoc_url` and `openapi_url` are `None`, so `/docs`,
  `/redoc` and `/openapi.json` answer 404.
- Adds the CORS middleware only when `CORS_ORIGINS` is not empty.
- Exposes a health check for monitoring.

## Endpoint

| Endpoint | Description |
| --- | --- |
| `GET /health` | Returns `{"status": "healthy"}` with status 200 |

The endpoint is excluded from the OpenAPI schema.

## Settings

Implemented by `webhooks.config.Settings` (pydantic-settings).

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Webhooks` | Application name, used as the FastAPI title |
| `LOG_LEVEL` | `INFO` | Python logging level (consumed by the logging feature) |
| `DOCS_ENABLED` | `false` | Expose `/docs`, `/redoc` and `/openapi.json` |
| `CORS_ORIGINS` | `[]` | Allowed origins, as a JSON list; CORS is off when empty |
| `CORS_CREDENTIALS` | `true` | Allow credentials in CORS requests |
| `CORS_METHODS` | `["*"]` | Allowed HTTP methods, as a JSON list |
| `CORS_HEADERS` | `["*"]` | Allowed request headers, as a JSON list |

## Data model

None. The application has no database and no migrations.

## How it is tested

Pytest (`apps/webhooks/tests/`):

- `test_main.py` - application title and version, disabled documentation
  endpoints, the health response and unknown paths over the ASGI transport,
  documentation URLs when `DOCS_ENABLED` is true, CORS middleware presence.
- `test_routes_health.py` - the `health_check` handler and the
  `HealthResponse` model.
- `test_config.py` - default values, environment overrides and
  case-insensitive names.

Behave (`apps/webhooks/features/health.feature`), run in-process through the
httpx ASGI transport, without any infrastructure:

- Health endpoint returns healthy status
- Unknown endpoint returns 404
- OpenAPI documentation is disabled

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
