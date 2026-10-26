# Application foundation

The foundation provides the workspace member, the settings class, the
FastAPI application object and the health endpoint. Every later feature
plugs into it.

## What it does

- Declares the `mta-sts` distribution (hatchling build, src layout, Python
  3.11 or later) with its import package `mta_sts`.
- Loads settings from the environment (and from a `.env` file when present).
- Creates the FastAPI application `mta_sts.main:app`. Swagger, ReDoc and the
  OpenAPI schema are disabled (`docs_url`, `redoc_url` and `openapi_url`
  are `None`), so `/docs`, `/redoc` and `/openapi.json` answer 404.
- Exposes a health check for monitoring.

## Endpoint

| Endpoint | Description |
| --- | --- |
| `GET /health` | Returns `{"status": "healthy"}` with status 200 |

The endpoint is excluded from the OpenAPI schema.

## Settings

Implemented by `mta_sts.config.Settings` (pydantic-settings).

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `mta-sts` | Application name, used as the FastAPI title |
| `LOG_LEVEL` | `INFO` | Python logging level (consumed by the logging feature) |

## Data model

None. The application has no database and no migrations.

## How it is tested

Pytest (`apps/mta-sts/tests/`):

- `test_main.py` - application title and version, disabled documentation
  endpoints, unknown paths, the `/health` handler and its HTTP response, the
  `HealthResponse` model and the version format.
- `test_config.py` - default values and environment overrides.

Behave (`apps/mta-sts/features/health.feature`), run in-process through the
httpx ASGI transport, without any infrastructure:

- Health endpoint returns healthy status
- Unknown endpoint returns 404
- OpenAPI documentation is disabled

```bash
uv run --package mta-sts pytest apps/mta-sts
uv run --package mta-sts behave apps/mta-sts/features
```
