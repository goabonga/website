# Foundation

The foundation is the smallest runnable server: a configuration object, an
application factory, a health endpoint and a CORS policy. Every later feature
extends it.

## What it provides

- `frontend.config.Settings`: pydantic-settings model read from environment
  variables (case-insensitive) and from a `.env` file in the working
  directory. `frontend.config.settings` is the instance built at import time.
- `frontend.main.create_app(settings=None)`: builds the FastAPI application
  from a `Settings` object (the module-level one by default). Tests and the
  behave scenarios call it with their own settings, so no global state needs
  patching. The settings used are kept on `app.state.settings`.
- `frontend.main.app`: the application built from the global settings, which
  is what gunicorn or uvicorn load.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status": "healthy"}`; used for monitoring and readiness probes. Hidden from the OpenAPI schema. |
| GET | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc and the schema. Only registered when `DOCS_ENABLED=true`; otherwise they answer `404`. |

## Settings

`apps/frontend/.env.example` lists every variable. List values are JSON.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `GOABONGA` | Title of the application |
| `DEBUG` | `false` | FastAPI debug mode |
| `DOCS_ENABLED` | `false` | Expose Swagger UI, ReDoc and the OpenAPI schema |
| `CORS_ORIGINS` | `["*"]` | Allowed origins |
| `CORS_CREDENTIALS` | `true` | Allow credentials |
| `CORS_METHODS` | `["*"]` | Allowed methods |
| `CORS_HEADERS` | `["*"]` | Allowed headers |

No variable is a secret. The application has no database, so there is no
migration.

## Running locally

```bash
uv sync --package frontend
cp apps/frontend/.env.example apps/frontend/.env
cd apps/frontend && uv run --package frontend uvicorn frontend.main:app --port 8000
```

## Tests

pytest (`tests/test_config.py`, `tests/test_main.py`) covers the defaults,
environment and `.env` overrides, the health endpoint, the documentation
switch and the CORS policy.

behave (`features/foundation.feature`) has these scenarios:

- Health check reports a healthy server
- API documentation is disabled by default
- API documentation can be enabled
- Cross-origin requests are allowed by default
- Cross-origin requests can be restricted to listed origins

`features/environment.py` builds one application per scenario from the
settings the scenario declares, and `features/steps/common_steps.py` holds the
steps shared by all features.
