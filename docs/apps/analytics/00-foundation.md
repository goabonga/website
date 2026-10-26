# Foundation

The foundation is the smallest runnable application: typed settings, dual
stream logging, the FastAPI application with CORS and the `/health` probe.
Every other feature plugs into it.

## What it does

- `analytics.config.Settings` loads settings from the environment and from a
  `.env` file in the working directory. Names are case-insensitive.
- `analytics.logging.setup_logging` sends `DEBUG` and `INFO` records to
  standard output and `WARNING` and above to standard error, so that systemd
  can write them to separate journals. Every record carries the request
  context (`sid=` and `ip=`) set with `set_request_context`.
- `analytics.main.app` is the ASGI application. It configures logging first,
  adds the CORS middleware and logs the start and the stop of the service in
  its lifespan handler.
- `GET /health` answers `{"status": "healthy"}` and is used by load balancer
  and monitoring probes. It is not part of the OpenAPI schema.

OpenAPI documentation (`/docs`, `/redoc`, `/openapi.json`) is only served when
`DOCS_ENABLED=true`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Analytics` | Application title |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DOCS_ENABLED` | `false` | Serve `/docs`, `/redoc` and `/openapi.json` |
| `CORS_ORIGINS` | `["*"]` | Allowed origins (JSON list) |
| `CORS_CREDENTIALS` | `true` | Allow credentials in CORS requests |
| `CORS_METHODS` | `["GET", "POST", "OPTIONS"]` | Allowed methods (JSON list) |
| `CORS_HEADERS` | `["*"]` | Allowed headers (JSON list) |

`apps/analytics/.env.example` lists the variables with working values.

## Run locally

From the repository root:

```bash
uv sync --package analytics
uv run --package analytics uvicorn analytics.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

The package pulls `uvicorn` and `gunicorn` as runtime dependencies: the
service is served by uvicorn locally and by gunicorn with uvicorn workers in
production.

## Tests

pytest (`apps/analytics/tests`):

- `test_config.py`: defaults, environment overrides, case-insensitive names.
- `test_logging.py`: stdout/stderr filters, context filter, `setup_logging`,
  `get_logger`, request context helpers.
- `test_routes_health.py`: the handler and the response model.
- `test_main.py`: title, disabled docs, CORS middleware, registered routes,
  version format and lifespan logging.

behave (`apps/analytics/features/health.feature`, in-process through
`httpx.ASGITransport`, no external service):

- Health endpoint returns healthy status
- Unknown endpoint returns 404

```bash
uv run --package analytics --group dev pytest apps/analytics
uv run --package analytics --group dev behave apps/analytics/features
```
