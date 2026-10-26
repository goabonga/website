# Application foundation

The foundation is the skeleton every other feature plugs into: the
configuration object, structured logging, the asynchronous database base
and the FastAPI application with its health probe.

## What it provides

| Module | Role |
|--------|------|
| `backend.config` | `Settings`, a `pydantic-settings` class read from environment variables and an optional `.env` file |
| `backend.logging` | Dual-stream logging and request-scoped logging context |
| `backend.database` | Async SQLAlchemy engine, session factory, `Base` and the `get_db` dependency |
| `backend.main` | The `app` object: CORS middleware, lifespan hook, `/health` |

### Endpoint

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Returns `{"status": "healthy"}`; hidden from the OpenAPI schema |

The probe does not touch the database, so it only proves that the process
serves requests. It is meant for load balancer and monitoring checks.

## Settings

Names are case-insensitive environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `GOABONGA API` | Title of the FastAPI application |
| `DEBUG` | `false` | Echo SQL statements from the engine |
| `LOG_LEVEL` | `INFO` | Root log level |
| `DOCS_ENABLED` | `false` | Expose `/docs`, `/redoc` and `/openapi.json` |
| `CORS_ORIGINS` | `["*"]` | Allowed origins (JSON list) |
| `CORS_CREDENTIALS` | `true` | Allow credentials in CORS requests |
| `CORS_METHODS` | `["*"]` | Allowed methods (JSON list) |
| `CORS_HEADERS` | `["*"]` | Allowed headers (JSON list) |
| `DATABASE_URL` | `postgresql://localhost/app` | PostgreSQL URL |

`DATABASE_URL` accepts `postgres://` and `postgresql://`; both are rewritten
to the `postgresql+asyncpg://` driver URL by
`get_async_database_url`.

## Logging

`setup_logging(level)` is called from the application lifespan. It installs
two handlers on the root logger: INFO and DEBUG records go to stdout,
WARNING and above go to stderr, so that systemd can route them to separate
journals. Every line carries the `user_id` and `client_id` of the current
request, taken from a context variable set with `set_request_context`.
`log_action` writes a structured `ACTION:` line. The `urllib3`, `httpx` and
`httpcore` loggers are limited to WARNING.

## Database base

`Base` is the declarative base shared by all models. `get_db` is a FastAPI
dependency that yields an `AsyncSession` (no expiry on commit) and always
closes it. The engine is created at import time and connects lazily, so
importing the package never needs a running database.

## Running locally

```bash
uv run --package backend uvicorn backend.main:app --reload
curl http://127.0.0.1:8000/health
```

## Tests

- pytest: `tests/test_config.py`, `tests/test_main.py`,
  `tests/test_logging.py`, `tests/test_database.py`.
- behave: `features/health.feature` (scenarios "Health check returns
  healthy status" and "Health check response has correct structure"). The
  scenarios drive the application through the Starlette test client, with
  no external service.
