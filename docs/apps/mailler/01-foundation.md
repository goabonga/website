# Application foundation

The base every other feature builds on: configuration, logging, database
session factories, the FastAPI application and a health check.

## What it provides

- `mailler.config.Settings` (pydantic-settings) and the `settings` singleton.
- `mailler.logging`: dual-stream logging (INFO and DEBUG to stdout, WARNING
  and above to stderr) with a request context carrying `user_id` and
  `client_id`.
- `mailler.database`: an asynchronous engine and session factory for the API
  (`get_db`, `get_async_db`) and a synchronous engine and session factory for
  Celery workers (`get_sync_db`). Both are built from the same `DATABASE_URL`;
  the `asyncpg` driver suffix is added or stripped as needed.
- `mailler.models.base.Base`, the SQLAlchemy declarative base.
- `mailler.main:app`, the FastAPI application with CORS middleware.

## Endpoints

| Endpoint | Method | Authentication | Description |
| --- | --- | --- | --- |
| `/health` | GET | none | Returns `{"status": "healthy"}`; hidden from the OpenAPI schema. |

`/docs`, `/redoc` and `/openapi.json` are only served when `DOCS_ENABLED` is
true.

## Settings

Settings are read from environment variables and from a `.env` file in the
working directory. Unknown variables are ignored.

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Mailler API` | Application name |
| `LOG_LEVEL` | `INFO` | Log level |
| `DOCS_ENABLED` | `false` | Serve `/docs`, `/redoc` and `/openapi.json` |
| `DATABASE_ECHO` | `false` | Log SQL statements |
| `DATABASE_URL` | `postgresql:///mailler` | PostgreSQL URL |
| `CORS_ORIGINS` | `[]` | Allowed origins (JSON list); no origin is allowed until configured |
| `CORS_CREDENTIALS` | `true` | Allow credentials |
| `CORS_METHODS` | `["*"]` | Allowed methods (JSON list) |
| `CORS_HEADERS` | `["*"]` | Allowed headers (JSON list) |

Later features add their own settings; each page lists the ones it
introduces.

## Dependencies

The package depends on FastAPI, pydantic and pydantic-settings, SQLAlchemy
(asyncio extra, pinned below 2.1), `asyncpg` for the API and `psycopg2-binary`
for workers. `uvicorn` and `gunicorn` are the ASGI servers used to run the
application.

## How it is tested

- pytest: `tests/test_config.py`, `tests/test_logging.py`,
  `tests/test_database.py`, `tests/test_main.py`,
  `tests/test_routes_health.py`.
- behave: `features/foundation.feature` (health check, documentation
  disabled by default, unknown routes, CORS preflight).
