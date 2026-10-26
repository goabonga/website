# Application foundation

The foundation is the smallest runnable version of the service: a FastAPI
application with typed settings, logging, an async database session factory,
a health check and a root endpoint. Every later feature plugs into it.

## What it adds

- The `custom-domain` uv workspace member (`apps/custom-domain`, import package
  `custom_domain`, version `0.0.0`).
- `custom_domain.main:app`, the ASGI application. Its lifespan logs start and
  stop and disposes the database engine on shutdown.
- `custom_domain.config.settings`, a Pydantic Settings object read from the
  environment or from a `.env` file.
- `custom_domain.logging`, a logging setup that sends `INFO` and `DEBUG` records
  to stdout and `WARNING` and above to stderr, plus request-scoped context
  helpers.
- `custom_domain.database`, an async SQLAlchemy engine and session factory
  (`asyncpg`), the `get_db` FastAPI dependency and the `get_async_db` context
  manager.
- A catch-all exception handler that logs the traceback and answers with a
  JSON `500`.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Returns `{"status": "healthy"}`. |
| `/` | GET | Returns the service name, its version and the documentation URL (`null` when disabled). |

The interactive documentation (`/docs`, `/redoc`, `/openapi.json`) is only
served when `DOCS_ENABLED=true`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Custom Domain Service` | Display name of the service. |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `DOCS_ENABLED` | `false` | Serve Swagger UI, ReDoc and the OpenAPI document. |
| `DATABASE_ECHO` | `false` | Log every SQL statement. |
| `DATABASE_URL` | `postgresql:///custom_domain` | PostgreSQL URL. A plain `postgresql://` URL is converted to `postgresql+asyncpg://` by the application. |
| `DATABASE_POOL_SIZE` | `5` | Connections kept open by the engine (the worker's synchronous engine uses the same value). |
| `DATABASE_MAX_OVERFLOW` | `10` | Extra connections the engine may open under load. |
| `CORS_ORIGINS` | `[]` | Allowed origins as a JSON list. The CORS middleware is only installed when the list is not empty. |
| `CORS_CREDENTIALS` | `true` | Allow credentials in cross-origin requests. |
| `CORS_METHODS` | `["*"]` | Allowed HTTP methods. |
| `CORS_HEADERS` | `["*"]` | Allowed request headers. |

## How it is tested

- pytest: `test_config.py`, `test_logging.py`, `test_database.py`,
  `test_health.py`, `test_routes_health.py` and `test_main.py` (lifespan,
  CORS, exception handler, root endpoint, application metadata).
- behave: `features/foundation.feature` with the scenarios *Health check reports
  the service as healthy*, *Root endpoint describes the service* and
  *Interactive documentation is disabled by default*. The scenarios call the
  ASGI application in-process, no database or Redis is needed.

```bash
uv run --package custom-domain --group dev pytest apps/custom-domain
uv run --package custom-domain --group dev behave apps/custom-domain/features
```
