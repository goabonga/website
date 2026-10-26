# Application foundation

The foundation provides the workspace member, the settings class, the
FastAPI application object, the CORS configuration and the health endpoint.
Every later feature plugs into it.

## What it does

- Declares the `reachy-mini-api` distribution (hatchling build, src layout,
  Python 3.11 or later) with its import package `reachy_mini_api`.
- Loads settings from the environment (and from a `.env` file when present).
- Creates the FastAPI application `reachy_mini_api.main:app`.
- Adds the CORS middleware configured from the settings.
- Serves Swagger (`/docs`), ReDoc (`/redoc`) and the OpenAPI schema
  (`/openapi.json`) only when `DOCS_ENABLED` is true. By default they are
  disabled and answer 404.
- Exposes a health check for monitoring.

## Endpoint

| Endpoint | Description |
| --- | --- |
| `GET /health` | Returns `{"status": "healthy"}` with status 200 |

The endpoint is excluded from the OpenAPI schema.

## Settings

Implemented by `reachy_mini_api.config.Settings` (pydantic-settings).
List values are given as JSON, for example `CORS_ORIGINS='["https://reachy.internal"]'`.

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Reachy Mini API` | Application name, used as the FastAPI title |
| `DEBUG` | `false` | Debug flag (declared for the deployment environment, not read by the code yet) |
| `DOCS_ENABLED` | `false` | Serve `/docs`, `/redoc` and `/openapi.json` |
| `CORS_ORIGINS` | `["*"]` | Allowed origins |
| `CORS_CREDENTIALS` | `true` | Allow credentials in cross-origin requests |
| `CORS_METHODS` | `["GET", "POST"]` | Allowed methods |
| `CORS_HEADERS` | `["*"]` | Allowed headers |

## Data model

None. The application has no database and no migrations.

## How it is tested

Pytest (`apps/reachy-mini-api/tests/`):

- `test_main.py` - application title and version, disabled documentation
  endpoints, unknown paths, CORS headers, the `/health` handler and its HTTP
  response, exclusion from the schema and the `HealthResponse` model.
- `test_config.py` - default values, environment overrides and `.env` file
  loading.

Behave (`apps/reachy-mini-api/features/health.feature`), run in-process
through the httpx ASGI transport, without any infrastructure:

- Health endpoint returns healthy status
- Unknown endpoint returns 404
- OpenAPI documentation is disabled

```bash
uv run --package reachy-mini-api pytest apps/reachy-mini-api
uv run --package reachy-mini-api behave apps/reachy-mini-api/features
```
