# Foundation

The foundation is the smallest runnable server: a settings object, logging, an
async database session factory, a health endpoint and a CORS policy. Every
later feature extends it.

## What it provides

- `team.config.Settings`: pydantic-settings model read from environment
  variables (case-insensitive) and from a `.env` file in the working
  directory. `team.config.get_settings()` returns a cached instance and
  `team.config.settings` is the instance built at import time.
- `team.config.get_credential(name, default)`: reads a secret first from the
  systemd credentials directory (`$CREDENTIALS_DIRECTORY/<name>`), then from
  the environment of the same name, then falls back to the default. Features
  that need a secret read it through this function, so the value never has to
  be written in the `.env` file.
- `team.main.app`: the FastAPI application, which is what gunicorn or uvicorn
  load (`team.main:app`). Its lifespan logs the start and the stop of the
  application.
- `team.database`: the async SQLAlchemy engine (`asyncpg` driver), the
  `async_session_factory` and the `get_db` dependency, which yields one session
  per request, commits when the request succeeds and rolls back when it fails.
  `team.models.base.Base` is the declarative base of every model and is kept in
  its own module so that tools can import it without creating an engine.
- `team.logging`: logging configuration that sends `DEBUG` and `INFO` records
  to stdout and `WARNING`, `ERROR` and `CRITICAL` records to stderr, so that
  systemd can capture them in two files. Every line carries the request
  context (`user`, `client`, `saas`), set with `set_request_context()` and
  cleared with `clear_request_context()`. `log_action()` writes an `ACTION:`
  line with details.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status": "healthy", "version": "<package version>"}`; no authentication, hidden from the OpenAPI schema. |
| GET | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc and the schema. Only registered when `DOCS_ENABLED=true` (the default of the code). |

## Settings

`apps/team/.env.example` lists every variable of the application; the ones
below belong to the foundation. List values are JSON.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `Team` | Title of the application |
| `DOCS_ENABLED` | `true` | Expose Swagger UI, ReDoc and the OpenAPI schema |
| `LOG_LEVEL` | `INFO` | Level of the root logger |
| `DATABASE_URL` | `postgresql+asyncpg://team:team@localhost:5432/team` | Async SQLAlchemy URL |
| `DATABASE_ECHO` | `false` | Log every SQL statement |
| `CORS_ORIGINS` | `["*"]` | Allowed origins (with credentials allowed, the response echoes the request origin) |
| `CORS_CREDENTIALS` | `true` | Allow credentials |
| `CORS_METHODS` | `["*"]` | Allowed methods |
| `CORS_HEADERS` | `["*"]` | Allowed headers |

No variable of the foundation is a secret. The foundation has no table, so it
has no migration yet; the first one comes with the teams feature.

## Running locally

```bash
uv sync --package team --group dev
cp apps/team/.env.example apps/team/.env
cd apps/team && uv run --package team uvicorn team.main:app --port 8000
```

## Tests

pytest (`tests/test_config.py`, `tests/test_database.py`, `tests/test_logging.py`,
`tests/test_main.py`, `tests/test_models.py`, `tests/test_routes_health.py`)
covers the defaults and the overrides of the settings, the credential lookup
order, the database session lifecycle (commit and rollback), every logging
filter and helper, the health endpoint and the application lifespan.
`tests/conftest.py` provides the `client` fixture (an httpx client bound to the
ASGI application, with a mocked database session) used by all route tests.

behave (`features/foundation.feature`) has these scenarios:

- Health check reports a healthy server
- API documentation is served by default
- Cross-origin requests are allowed by default
- Settings are read from the environment
- Settings have defaults for local development
- Secrets are read from the systemd credentials directory first
- Log records are split between stdout and stderr
- Log lines carry the request context

`features/environment.py` builds a client bound to the ASGI application for
each scenario and restores the logging configuration afterwards;
`features/steps/common_steps.py` holds the steps shared by all features.
