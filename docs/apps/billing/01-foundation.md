# Foundation

The foundation provides the runnable skeleton every other feature builds
on: the FastAPI application, settings, logging, the async database session
and a health endpoint.

## Application

`billing.main` builds the `app` object served as `billing.main:app`:

- the title comes from `APP_NAME`;
- the Swagger UI, ReDoc and `openapi.json` are served only when
  `DOCS_ENABLED=true` (they answer 404 otherwise);
- a CORS middleware is configured from the `CORS_*` settings;
- a lifespan handler logs the start and the shutdown of the service.

```bash
uv run --package billing uvicorn billing.main:app --reload --port 8000
```

## Endpoints

| Path | Method | Auth | Purpose |
|------|--------|------|---------|
| `/health` | GET | none | Liveness probe, returns `{"status": "healthy", "version": "..."}` |

The endpoint is hidden from the OpenAPI document.

## Configuration

`billing.config.Settings` reads environment variables (case insensitive) or
a `.env` file. Later features add their own variables; this page lists the
ones that exist at this point.

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_NAME` | `Billing API` | Title of the OpenAPI document |
| `DOCS_ENABLED` | `false` | Serve Swagger UI, ReDoc and `openapi.json` |
| `DATABASE_ECHO` | `false` | SQLAlchemy engine query logging |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | `[]` | Allowed origins (JSON list); empty means no cross-origin access |
| `CORS_CREDENTIALS` | `false` | Allow credentials |
| `CORS_METHODS` | `["*"]` | Allowed methods (JSON list) |
| `CORS_HEADERS` | `["*"]` | Allowed headers (JSON list) |
| `DATABASE_URL` | `postgresql+asyncpg://billing:billing@localhost:5432/billing` | Async PostgreSQL URL |
| `DATABASE_POOL_SIZE` | `10` | Connections kept open in the pool |
| `DATABASE_MAX_OVERFLOW` | `20` | Extra connections allowed above the pool size |

## Database session

`billing.database` creates the async SQLAlchemy engine (asyncpg driver,
pooled, pre-ping enabled) and exposes `get_db`, a FastAPI dependency that
yields an `AsyncSession`, commits when the request succeeds and rolls back
on error. `billing.models.base.Base` is the declarative base shared by all
models; the models themselves arrive with the data model feature.

## Logging

The web application configures the standard library logging with
`logging.basicConfig` at the level given by `LOG_LEVEL`.

`billing.logging` additionally provides a dual-stream configuration meant
for processes managed by systemd: `setup_logging` sends records up to
`INFO` to stdout and `WARNING` and above to stderr, so that the two can be
stored in separate files. A `ContextFilter` adds `user_id`, `client_id` and
`saas_id` taken from a request-scoped context (`set_request_context`,
`clear_request_context`), and `log_action` logs a named action with that
context. `setup_logging` is not called by `billing.main`.

## How it is tested

pytest (`apps/billing/tests`):

- `test_config.py`: defaults and environment overrides of `Settings`;
- `test_logging.py`: stream filters, request context, `setup_logging`;
- `test_database.py`: commit and rollback behaviour of `get_db`;
- `test_routes_health.py`: health response model and handler;
- `test_main.py`: registered routes, docs disabled by default, lifespan.

behave (`apps/billing/features/health.feature`):

- Health check returns healthy;
- Interactive API documentation is disabled by default.
